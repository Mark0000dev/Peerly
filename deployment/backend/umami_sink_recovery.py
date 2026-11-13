"""Guarded staging-only sink unblock. No provider calls or dead-delivery replay."""

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Literal, Never
from uuid import UUID, uuid4

from deployment.backend.canonical_backfill import guard_database, journal_descriptor
from deployment.backend.external_delivery_activation import Closed
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from studymate.application.external_delivery import recovery as application_recovery
from studymate.application.external_delivery.recovery import (
    RecoveryRejectedError,
    UmamiRecoveryState,
    UmamiRecoveryTarget,
    recover_umami_sink,
)
from studymate.domain.external_delivery.delivery import DestinationRef
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.external_delivery import recovery as infrastructure_recovery
from studymate.infrastructure.external_delivery.http_adapters.configuration import (
    UmamiConfig,
    target_fingerprint,
)
from studymate.infrastructure.external_delivery.recovery import SqlUmamiRecoveryTransaction

MAX_INPUT = 65536


class Target(Closed):
    schema_version: Literal[1]
    operation_id: UUID
    performed_by: str = Field(pattern=r"^[A-Za-z0-9_-]{1,38}$")
    database: Literal["peerly_staging"]
    database_schema: Literal["public"]
    migration_revision: Literal["0060_report_triage"]
    backend_image: str = Field(pattern=r"^ghcr\.io/mark0000dev/peerly-backend@sha256:[0-9a-f]{64}$")
    revision: int = Field(ge=1)
    origin: str
    website_id: UUID
    hostname: str
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    failed_delivery_id: UUID

    def configuration(self) -> UmamiConfig:
        result = UmamiConfig(
            DestinationRef(Sink.UMAMI, self.revision), self.origin, self.website_id, self.hostname
        )
        if target_fingerprint(result).hex() != self.fingerprint:
            raise RecoveryRejectedError("target_fingerprint_mismatch")
        return result

    def recovery_target(self) -> UmamiRecoveryTarget:
        self.configuration()
        return UmamiRecoveryTarget(
            self.revision, bytes.fromhex(self.fingerprint), self.failed_delivery_id
        )


class Plan(Closed):
    target: Target
    snapshot: UmamiRecoveryState
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def source_digest() -> str:
    files = (
        Path(__file__),
        Path(application_recovery.__file__),
        Path(infrastructure_recovery.__file__),
    )
    return hashlib.sha256(b"\x00".join(path.read_bytes() for path in files)).hexdigest()


def plan_digest(plan: Plan) -> str:
    return hashlib.sha256(
        json.dumps(
            plan.model_dump(mode="json", exclude={"plan_sha256"}),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def build_plan(target: Target, snapshot: UmamiRecoveryState, source_hash: str) -> Plan:
    if snapshot.blocked_reason != "destination_unavailable":
        raise RecoveryRejectedError("sink_not_destination_blocked")
    plan = Plan(target=target, snapshot=snapshot, source_sha256=source_hash, plan_sha256="0" * 64)
    return plan.model_copy(update={"plan_sha256": plan_digest(plan)})


def validate_plan(plan: Plan, source_hash: str) -> None:
    if plan.plan_sha256 != plan_digest(plan) or plan.source_sha256 != source_hash:
        raise RecoveryRejectedError("plan_or_source_hash_mismatch")
    plan.target.recovery_target()


def require_runtime(target: Target, runtime_image: str) -> None:
    if runtime_image != target.backend_image:
        raise RecoveryRejectedError("runtime_image_pin_mismatch")
    expected = {
        "UMAMI__REVISION": str(target.revision),
        "UMAMI__ORIGIN": target.origin,
        "UMAMI__WEBSITE_ID": str(target.website_id),
        "UMAMI__HOSTNAME": target.hostname,
    }
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RecoveryRejectedError("runtime_umami_configuration_mismatch")


def private_read(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_uid not in {0, os.geteuid()}
        ):
            raise RecoveryRejectedError("unsafe_input_file")
        raw = os.read(descriptor, MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise RecoveryRejectedError("input_too_large")
        return raw
    finally:
        os.close(descriptor)


def retain_journal(directory: Path, name: str, value: dict[str, object]) -> None:
    """Private durable no-replace journal, not a transactional application audit."""
    descriptor = journal_descriptor(directory)
    temporary = uuid4().hex + ".tmp"
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        item = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=descriptor,
        )
        with os.fdopen(item, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(
                temporary, name, src_dir_fd=descriptor, dst_dir_fd=descriptor, follow_symlinks=False
            )
        except FileExistsError:
            if private_read(directory / name) != raw:
                raise RecoveryRejectedError("operation_journal_rebind") from None
        os.fsync(descriptor)
    finally:
        try:
            os.unlink(temporary, dir_fd=descriptor)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


async def run(
    command: Literal["plan", "apply", "inspect"],
    value: Target | Plan,
    source_hash: str,
    runtime_image: str,
) -> dict[str, object]:
    if isinstance(value, Plan):
        validate_plan(value, source_hash)
    target = value.target if isinstance(value, Plan) else value
    require_runtime(target, runtime_image)
    url = os.environ.get("DATABASE_URL", "")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or parsed.database != target.database:
        raise RecoveryRejectedError("wrong_database_configuration")
    engine = create_async_engine(
        url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
        connect_args={
            "timeout": 5,
            "server_settings": {
                "search_path": "public",
                "statement_timeout": "5000",
                "lock_timeout": "1000",
            },
        },
    )
    try:
        async with (
            asyncio.timeout(30),
            async_sessionmaker(engine, expire_on_commit=False).begin() as session,
        ):
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            if command != "apply":
                await session.execute(text("SET TRANSACTION READ ONLY"))
            await guard_database(session)
            transaction = SqlUmamiRecoveryTransaction(session)
            if command == "apply":
                if not isinstance(value, Plan):
                    raise RecoveryRejectedError("approved_plan_required")
                validate_plan(value, source_hash)
                observed = await recover_umami_sink(
                    transaction, target.recovery_target(), value.snapshot
                )
                result: dict[str, object] = {
                    "status": "sink_unblocked",
                    "plan_sha256": value.plan_sha256,
                    "observed_at": observed.observed_at.isoformat(),
                }
            else:
                observed = await transaction.inspect(target.recovery_target(), lock=False)
                if command == "plan":
                    return build_plan(target, observed, source_hash).model_dump(mode="json")
                result = {
                    "status": "state_observed",
                    "blocked_reason": observed.blocked_reason,
                    "commit_attribution": "unknown",
                }
        result.update(
            operation_id=str(target.operation_id),
            performed_by=target.performed_by,
            failed_delivery_id=str(target.failed_delivery_id),
            source_sha256=source_hash,
            backend_image=target.backend_image,
            provider_calls=0,
            dead_delivery_preserved=True,
            receipt_scope="Operational journal; not transactional canonical/operator audit",
        )
        return result
    finally:
        await engine.dispose()


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RecoveryRejectedError("invalid_arguments")


def main() -> int:
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("command", choices=("plan", "apply", "inspect"))
        parser.add_argument("--input", type=Path, required=True)
        parser.add_argument("--runtime-image", required=True)
        parser.add_argument("--journal", type=Path)
        args = parser.parse_args()
        source_hash = source_digest()
        raw = private_read(args.input)
        value = (
            Plan.model_validate_json(raw)
            if args.command != "plan"
            else Target.model_validate_json(raw)
        )
        if args.command == "apply":
            if not isinstance(value, Plan) or args.journal is None:
                raise RecoveryRejectedError("approved_plan_and_journal_required")
            validate_plan(value, source_hash)
            require_runtime(value.target, args.runtime_image)
            retain_journal(
                args.journal,
                value.target.operation_id.hex + ".intent.json",
                value.model_dump(mode="json"),
            )
        result = asyncio.run(run(args.command, value, source_hash, args.runtime_image))
        if args.command == "apply" and isinstance(value, Plan):
            retain_journal(args.journal, value.target.operation_id.hex + ".receipt.json", result)
    except RecoveryRejectedError as error:
        result = {"status": "rejected", "code": str(error)}
        code = 1
    except (ValueError, OSError, SQLAlchemyError, TimeoutError):
        result = {
            "status": "unconfirmed",
            "code": "invalid_input_or_storage_unavailable",
            "recovery": "No blind apply retry; inspect the same approved plan read-only",
        }
        code = 1
    else:
        code = 0
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
