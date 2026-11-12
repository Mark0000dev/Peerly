"""Explicit staging-only canonical reference backfill. No provider, routing or replay."""

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Never
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from studymate.application.external_delivery.maintenance import (
    BACKFILL_BATCH,
    MaintenanceTransaction,
    SeedUmamiBackfill,
)
from studymate.domain.external_delivery.sources import CaptureMode
from studymate.domain.operator.timeline import OperatorEventKind
from studymate.infrastructure.external_delivery.maintenance import SqlMaintenanceTransaction
from studymate.infrastructure.external_delivery.materialization import database_now
from studymate.infrastructure.external_delivery.models import DeliverySourceRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.schema import MODELS

EXPECTED_DATABASE = "peerly_staging"
EXPECTED_REVISION = "0060_report_triage"
MAX_INPUT = 65536
if not MODELS:
    raise RuntimeError("Actual application model registry is required; no schema is created")


class BackfillRejectedError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class Closed(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)


class CanonicalRef(Closed):
    id: UUID
    kind: OperatorEventKind
    occurred_at: datetime


class Manifest(Closed):
    schema_version: Literal[1] = 1
    operation_id: UUID
    performed_by: str = Field(pattern=r"^[A-Za-z0-9_-]{1,38}$")
    database: Literal["peerly_staging"] = "peerly_staging"
    database_schema: Literal["public"] = "public"
    migration_revision: Literal["0060_report_triage"] = "0060_report_triage"
    cutoff: datetime
    planned_at: datetime
    helper_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sources: tuple[CanonicalRef, ...] = Field(max_length=BACKFILL_BATCH)
    more: bool


class Plan(Closed):
    status: Literal["planned"] = "planned"
    manifest: Manifest
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def helper_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def manifest_digest(manifest: Manifest) -> str:
    return hashlib.sha256(
        json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_plan(plan: Plan) -> None:
    manifest = plan.manifest
    if manifest_digest(manifest) != plan.manifest_sha256:
        raise BackfillRejectedError("manifest_fingerprint_mismatch")
    if manifest.helper_sha256 != helper_digest():
        raise BackfillRejectedError("helper_revision_mismatch")
    dates = (manifest.cutoff, manifest.planned_at, *(row.occurred_at for row in manifest.sources))
    if any(value.utcoffset() is None for value in dates):
        raise BackfillRejectedError("timezone_required")
    if manifest.cutoff > manifest.planned_at:
        raise BackfillRejectedError("future_cutoff")
    ids = tuple(row.id for row in manifest.sources)
    if ids != tuple(sorted(set(ids))):
        raise BackfillRejectedError("sources_not_unique_and_sorted")
    if any(row.occurred_at > manifest.cutoff for row in manifest.sources):
        raise BackfillRejectedError("source_after_cutoff")
    if manifest.more and len(ids) != BACKFILL_BATCH:
        raise BackfillRejectedError("invalid_more_marker")


async def guard_database(session: AsyncSession) -> None:
    row = (await session.execute(text("SELECT current_database(), current_schema()"))).one()
    if tuple(row) != (EXPECTED_DATABASE, "public"):
        raise BackfillRejectedError("wrong_database_or_schema")
    versions = tuple((await session.scalars(text("SELECT version_num FROM alembic_version"))).all())
    if versions != (EXPECTED_REVISION,):
        raise BackfillRejectedError("schema_revision_mismatch")


async def make_plan(
    session: AsyncSession,
    operation_id: UUID,
    performed_by: str,
    cutoff: datetime,
) -> Plan:
    at = await database_now(session)
    if cutoff.utcoffset() is None or cutoff > at:
        raise BackfillRejectedError("invalid_cutoff")
    captured = exists().where(DeliverySourceRecord.canonical_event_id == ProductEventRecord.id)
    rows = (
        await session.execute(
            select(ProductEventRecord.id, ProductEventRecord.kind, ProductEventRecord.occurred_at)
            .where(~captured, ProductEventRecord.occurred_at <= cutoff)
            .order_by(ProductEventRecord.id)
            .limit(BACKFILL_BATCH + 1)
        )
    ).all()
    manifest = Manifest(
        operation_id=operation_id,
        performed_by=performed_by,
        cutoff=cutoff,
        planned_at=at,
        helper_sha256=helper_digest(),
        more=len(rows) > BACKFILL_BATCH,
        sources=tuple(
            CanonicalRef(id=identifier, kind=OperatorEventKind(kind), occurred_at=when)
            for identifier, kind, when in rows[:BACKFILL_BATCH]
        ),
    )
    plan = Plan(manifest=manifest, manifest_sha256=manifest_digest(manifest))
    validate_plan(plan)
    return plan


@dataclass(frozen=True, slots=True)
class BoundMaintenanceUnit:
    """Reuse the accepted use case inside the caller's single atomic transaction."""

    session: AsyncSession

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[MaintenanceTransaction]:
        yield SqlMaintenanceTransaction(self.session)


async def apply_plan(session: AsyncSession, plan: Plan) -> dict[str, object]:
    validate_plan(plan)
    refs = plan.manifest.sources
    ids = tuple(row.id for row in refs)
    if ids:
        rows = (
            await session.execute(
                select(
                    ProductEventRecord.id, ProductEventRecord.kind, ProductEventRecord.occurred_at
                )
                .where(ProductEventRecord.id.in_(ids))
                .order_by(ProductEventRecord.id)
                .with_for_update(read=True)
            )
        ).all()
        actual = tuple(
            CanonicalRef(id=i, kind=OperatorEventKind(k), occurred_at=at) for i, k, at in rows
        )
        if actual != refs:
            raise BackfillRejectedError("canonical_selection_changed_or_missing")
        inserted = await SeedUmamiBackfill(BoundMaintenanceUnit(session))(ids)
        captures = tuple(
            (
                await session.scalars(
                    select(DeliverySourceRecord)
                    .where(DeliverySourceRecord.canonical_event_id.in_(ids))
                    .order_by(DeliverySourceRecord.canonical_event_id)
                )
            ).all()
        )
        if len(captures) != len(ids):
            raise BackfillRejectedError("capture_receipt_incomplete")
        for capture in captures:
            if capture.source_kind != "canonical" or capture.mode not in {"live", "backfill_umami"}:
                raise BackfillRejectedError("existing_capture_contract_mismatch")
    else:
        inserted, captures = 0, ()
    observed_database, at = (
        await session.execute(text("SELECT current_database(), clock_timestamp()"))
    ).one()
    if not isinstance(observed_database, str) or not isinstance(at, datetime):
        raise BackfillRejectedError("invalid_database_receipt")
    return {
        "status": "captured",
        "operation_id": str(plan.manifest.operation_id),
        "performed_by": plan.manifest.performed_by,
        "manifest_sha256": plan.manifest_sha256,
        "helper_sha256": helper_digest(),
        "database": observed_database,
        "migration_revision": EXPECTED_REVISION,
        "cutoff": plan.manifest.cutoff.isoformat(),
        "observed_at": at.isoformat(),
        "selected": len(ids),
        "inserted_this_transaction": inserted,
        "already_captured": len(ids) - inserted,
        "captures": [
            {
                "canonical_event_id": str(row.canonical_event_id),
                "capture_id": str(row.id),
                "mode": CaptureMode(row.mode).value,
                "captured_at": row.captured_at.isoformat(),
            }
            for row in captures
        ],
        "materialized": False,
        "provider_calls": 0,
        "telegram_backfill": False,
        "receipt_scope": (
            "Current retained mappings; operation label is operator-supplied, "
            "not a fabricated app audit or proof of first commit ownership"
        ),
    }


def read_plan(path: Path) -> Plan:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        return plan_from_descriptor(descriptor)
    finally:
        os.close(descriptor)


def plan_from_descriptor(descriptor: int) -> Plan:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o077
        or metadata.st_uid not in {0, os.geteuid()}
    ):
        raise BackfillRejectedError("unsafe_plan_file")
    raw = os.read(descriptor, MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise BackfillRejectedError("plan_too_large")
    plan = Plan.model_validate_json(raw)
    validate_plan(plan)
    return plan


def journal_descriptor(directory: Path) -> int:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    metadata = os.fstat(descriptor)
    if metadata.st_mode & 0o077 or metadata.st_uid not in {0, os.geteuid()}:
        os.close(descriptor)
        raise BackfillRejectedError("unsafe_journal_directory")
    return descriptor


def existing_intent(directory: Path, operation_id: UUID) -> Plan | None:
    descriptor = journal_descriptor(directory)
    try:
        try:
            item = os.open(
                operation_id.hex + ".json",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=descriptor,
            )
        except FileNotFoundError:
            return None
        try:
            plan = plan_from_descriptor(item)
            if plan.manifest.operation_id != operation_id:
                raise BackfillRejectedError("journal_operation_mismatch")
            return plan
        finally:
            os.close(item)
    finally:
        os.close(descriptor)


def bind_intent(directory: Path, plan: Plan) -> None:
    """Atomically retain the exact plan before any DB write; never replace an intent."""
    validate_plan(plan)
    descriptor = journal_descriptor(directory)
    temporary = plan.manifest.operation_id.hex + "." + uuid4().hex + ".tmp"
    name = plan.manifest.operation_id.hex + ".json"
    try:
        item = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=descriptor,
        )
        with os.fdopen(item, "w", encoding="utf-8") as output:
            output.write(plan.model_dump_json() + "\n")
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(
                temporary, name, src_dir_fd=descriptor, dst_dir_fd=descriptor, follow_symlinks=False
            )
        except FileExistsError:
            prior = existing_intent(directory, plan.manifest.operation_id)
            if prior is None or prior != plan:
                raise BackfillRejectedError("operation_intent_rebind") from None
        os.fsync(descriptor)
    finally:
        try:
            os.unlink(temporary, dir_fd=descriptor)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


async def run(
    command: Literal["plan", "apply"],
    *,
    operation_id: UUID | None = None,
    performed_by: str | None = None,
    cutoff: datetime | None = None,
    plan: Plan | None = None,
) -> dict[str, object]:
    url = os.environ.get("DATABASE_URL", "")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or parsed.database != EXPECTED_DATABASE:
        raise BackfillRejectedError("wrong_database_configuration")
    engine = create_async_engine(
        url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
        connect_args={
            "timeout": 5,
            "server_settings": {
                "search_path": "public",
                "lock_timeout": "1000",
                "statement_timeout": "5000",
            },
        },
    )
    try:
        async with (
            asyncio.timeout(30),
            async_sessionmaker(engine, expire_on_commit=False).begin() as session,
        ):
            if command == "plan":
                await session.execute(text("SET TRANSACTION READ ONLY"))
            await guard_database(session)
            if command == "plan":
                if operation_id is None or performed_by is None or cutoff is None:
                    raise BackfillRejectedError("plan_arguments_required")
                result = (await make_plan(session, operation_id, performed_by, cutoff)).model_dump(
                    mode="json"
                )
            else:
                if plan is None:
                    raise BackfillRejectedError("approved_plan_required")
                result = await apply_plan(session, plan)
        # Return a success receipt only after the outer transaction actually commits.
        return result
    finally:
        await engine.dispose()


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise BackfillRejectedError("invalid_arguments")


def main() -> int:
    try:
        parser = SafeParser(description=__doc__)
        commands = parser.add_subparsers(dest="command", required=True)
        planner = commands.add_parser("plan")
        planner.add_argument("--operation-id", type=UUID, required=True)
        planner.add_argument("--performed-by", required=True)
        planner.add_argument("--cutoff", type=datetime.fromisoformat, required=True)
        planner.add_argument("--journal-dir", type=Path, required=True)
        applier = commands.add_parser("apply")
        applier.add_argument("--plan", type=Path, required=True)
        applier.add_argument("--journal-dir", type=Path, required=True)
        args = parser.parse_args()
        if args.command == "plan":
            prior = existing_intent(args.journal_dir, args.operation_id)
            if prior is not None:
                if (
                    prior.manifest.performed_by != args.performed_by
                    or prior.manifest.cutoff != args.cutoff
                ):
                    raise BackfillRejectedError("operation_intent_rebind")
                result = prior.model_dump(mode="json")
            else:
                result = asyncio.run(
                    run(
                        "plan",
                        operation_id=args.operation_id,
                        performed_by=args.performed_by,
                        cutoff=args.cutoff,
                    )
                )
                plan = Plan.model_validate_json(json.dumps(result))
                bind_intent(args.journal_dir, plan)
        else:
            plan = read_plan(args.plan)
            bind_intent(args.journal_dir, plan)
            result = asyncio.run(run("apply", plan=plan))
    except BackfillRejectedError as error:
        result = {"status": "rejected", "code": error.code}
        code = 1
    except (ValueError, OSError, SQLAlchemyError, TimeoutError):
        result = {
            "status": "unconfirmed",
            "code": "invalid_input_or_storage_unavailable",
            "recovery": (
                "Reconcile retained capture mappings for the SAME approved manifest before retry; "
                "never widen cutoff or select new IDs blindly"
            ),
        }
        code = 1
    else:
        code = 0
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
