"""Staging target plan/register/check only. No worker start, queue mutation or HTTP."""

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Never
from uuid import UUID

from deployment.backend.canonical_backfill import guard_database
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from studymate.domain.external_delivery.delivery import DestinationRef
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.external_delivery.destinations import (
    DestinationRegistration,
    register_transaction_destinations,
)
from studymate.infrastructure.external_delivery.http_adapters.configuration import (
    TelegramConfig,
    UmamiConfig,
    target_fingerprint,
)
from studymate.infrastructure.external_delivery.models import (
    DeliveryDestinationRecord,
    DeliveryScheduleRecord,
)

MAX_INPUT = 65536
AFTER_ROW_INSERT = 5
MAX_REGISTRY_ROWS = 64
EXPECTED_CAPTURE_BODY_MD5 = "81b11edc2fd89526dbcbb555fddb9286"
type SinkName = Literal["umami", "telegram_support"]


class ActivationRejectedError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class Closed(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)


class UmamiTarget(Closed):
    revision: int = Field(ge=1)
    origin: str
    website_id: UUID


class SupportTarget(Closed):
    revision: int = Field(ge=1)
    chat_id: int
    operator_origin: str
    topic_id: int | None


class Targets(Closed):
    schema_version: Literal[1]
    database: Literal["peerly_staging"]
    database_schema: Literal["public"]
    migration_revision: Literal["0060_report_triage"]
    backend_image: str = Field(pattern=r"^ghcr\.io/mark0000dev/peerly-backend@sha256:[0-9a-f]{64}$")
    support_notice_not_before: datetime
    umami: UmamiTarget
    telegram_support: SupportTarget


class Registered(Closed):
    sink: SinkName
    revision: int
    fingerprint: str
    registered_at: datetime


class Schedule(Closed):
    sink: SinkName
    turn: int
    blocked: bool
    cooldown_until: datetime | None


class Snapshot(Closed):
    captured_at: datetime
    registered: tuple[Registered, ...] = Field(max_length=MAX_REGISTRY_ROWS)
    schedules: tuple[Schedule, ...] = Field(max_length=2)
    capture_triggers_verified: bool
    unsettled_deliveries: int = Field(ge=0)
    unresolved_attempts: int = Field(ge=0)
    pending_other_revision: int = Field(ge=0)
    old_support_notices: int = Field(ge=0)
    pending_sources: int = Field(ge=0)


class Plan(Closed):
    status: Literal["planned"] = "planned"
    targets: Targets
    targets_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    helper_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot: Snapshot


def helper_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def targets_digest(targets: Targets) -> str:
    return hashlib.sha256(
        json.dumps(targets.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def plan_digest(plan: Plan) -> str:
    return hashlib.sha256(
        json.dumps(
            plan.model_dump(mode="json", exclude={"plan_sha256"}),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def build_plan(targets: Targets, snapshot: Snapshot) -> Plan:
    content: dict[str, object] = {
        "status": "planned",
        "targets": targets.model_dump(mode="json"),
        "targets_sha256": targets_digest(targets),
        "helper_sha256": helper_digest(),
        "snapshot": snapshot.model_dump(mode="json"),
    }
    digest = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return Plan.model_validate_json(json.dumps(dict(content, plan_sha256=digest)))


def sink_name(value: str) -> SinkName:
    if value == "umami":
        return "umami"
    if value == "telegram_support":
        return "telegram_support"
    raise ActivationRejectedError("unknown_sink")


def registrations(targets: Targets) -> tuple[DestinationRegistration, ...]:
    umami, support = targets.umami, targets.telegram_support
    configurations = (
        UmamiConfig(DestinationRef(Sink.UMAMI, umami.revision), umami.origin, umami.website_id),
        TelegramConfig(
            DestinationRef(Sink.TELEGRAM_SUPPORT, support.revision),
            support.chat_id,
            support.operator_origin,
            topic_id=support.topic_id,
        ),
    )
    return tuple(
        DestinationRegistration(value.destination, target_fingerprint(value))
        for value in configurations
    )


def target_states(targets: Targets, snapshot: Snapshot) -> tuple[str, ...]:
    states: list[str] = []
    for item in registrations(targets):
        existing = tuple(
            row
            for row in snapshot.registered
            if (row.sink, row.revision) == (item.destination.sink.value, item.destination.revision)
        )
        if not existing:
            states.append("new")
        elif len(existing) == 1 and existing[0].fingerprint == item.fingerprint.hex():
            states.append("matching")
        else:
            raise ActivationRejectedError("registered_target_mismatch")
    return tuple(states)


def require_snapshot(targets: Targets, snapshot: Snapshot, *, registered: bool) -> None:
    dates = (
        targets.support_notice_not_before,
        snapshot.captured_at,
        *(row.cooldown_until for row in snapshot.schedules if row.cooldown_until is not None),
    )
    if any(at.utcoffset() is None for at in dates):
        raise ActivationRejectedError("timezone_required")
    if targets.support_notice_not_before > snapshot.captured_at:
        raise ActivationRejectedError("future_support_cutoff")
    if not snapshot.capture_triggers_verified:
        raise ActivationRejectedError("capture_trigger_mismatch")
    if {row.sink for row in snapshot.schedules} != {"umami", "telegram_support"} or {
        row.turn for row in snapshot.schedules
    } != {0, 1}:
        raise ActivationRejectedError("sink_schedule_mismatch")
    if any(row.blocked for row in snapshot.schedules):
        raise ActivationRejectedError("blocked_sink_requires_review")
    if any(
        row.cooldown_until is not None and row.cooldown_until > snapshot.captured_at
        for row in snapshot.schedules
    ):
        raise ActivationRejectedError("sink_cooldown_active")
    if snapshot.unsettled_deliveries or snapshot.unresolved_attempts:
        raise ActivationRejectedError("unsettled_work_requires_review")
    if snapshot.pending_other_revision:
        raise ActivationRejectedError("other_revision_work_requires_review")
    if snapshot.old_support_notices:
        raise ActivationRejectedError("historical_support_requires_review")
    states = target_states(targets, snapshot)
    if registered and any(state != "matching" for state in states):
        raise ActivationRejectedError("target_registration_required")


def validate_plan(plan: Plan, now: datetime) -> None:
    if (
        plan.targets_sha256 != targets_digest(plan.targets)
        or plan.helper_sha256 != helper_digest()
        or plan.plan_sha256 != plan_digest(plan)
    ):
        raise ActivationRejectedError("approved_plan_fingerprint_mismatch")
    require_snapshot(plan.targets, plan.snapshot, registered=False)
    if now.utcoffset() is None or not timedelta(
        seconds=-5
    ) <= now - plan.snapshot.captured_at <= timedelta(minutes=5):
        raise ActivationRejectedError("approved_snapshot_stale_or_future")


async def read_registered(session: AsyncSession) -> tuple[Registered, ...]:
    rows = tuple(
        (
            await session.scalars(
                select(DeliveryDestinationRecord)
                .order_by(DeliveryDestinationRecord.sink, DeliveryDestinationRecord.revision)
                .limit(MAX_REGISTRY_ROWS + 1)
            )
        ).all()
    )
    if len(rows) > MAX_REGISTRY_ROWS:
        raise ActivationRejectedError("registry_snapshot_bound")
    return tuple(
        Registered(
            sink=sink_name(row.sink),
            revision=row.revision,
            fingerprint=row.fingerprint.hex(),
            registered_at=row.registered_at,
        )
        for row in rows
    )


async def capture_triggers_verified(session: AsyncSession) -> bool:
    rows = (
        await session.execute(
            text("""
        SELECT c.relname, t.tgname, CAST(t.tgenabled AS text), t.tgtype, pn.nspname,
               p.proname, encode(t.tgargs,'hex'), md5(p.prosrc), n.nspname
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_proc p ON p.oid=t.tgfoid
        JOIN pg_namespace pn ON pn.oid=p.pronamespace
        WHERE NOT t.tgisinternal AND n.nspname=current_schema()
          AND t.tgname IN ('peerly_capture_product_events',
                          'peerly_capture_client_observations','peerly_capture_support_cases')
        ORDER BY c.relname LIMIT 4
    """)
        )
    ).all()
    expected = {
        ("product_events", "canonical", "canonical_event_id"),
        ("client_observations", "client_observation", "observation_id"),
        ("support_cases", "support_case", "support_case_id"),
    }
    if len(rows) != len(expected):
        return False
    for table, kind, column in expected:
        matching = [row for row in rows if row[0] == table and row[1] == "peerly_capture_" + table]
        if len(matching) != 1:
            return False
        row = matching[0]
        if (
            row[2] not in {"O", "A"}
            or row[3] != AFTER_ROW_INSERT
            or row[4] != row[8]
            or row[5] != "peerly_capture_external_source"
            or row[6] != (kind + "\0" + column + "\0").encode().hex()
            or row[7] != EXPECTED_CAPTURE_BODY_MD5
        ):
            return False
    return True


async def read_snapshot(session: AsyncSession, targets: Targets) -> Snapshot:
    registered = await read_registered(session)
    schedules = tuple(
        (
            await session.scalars(
                select(DeliveryScheduleRecord).order_by(DeliveryScheduleRecord.sink)
            )
        ).all()
    )
    counts = (
        (
            await session.execute(
                text("""
        SELECT clock_timestamp() AS captured_at,
          (SELECT count(*) FROM external_deliveries
           WHERE state IN ('leased','retry','dead')) AS unsettled_deliveries,
          (SELECT count(*) FROM external_delivery_attempts a
           JOIN external_deliveries d ON d.id=a.delivery_id
           WHERE d.state<>'succeeded'
             AND (a.ended_at IS NULL OR a.outcome IN ('ambiguous','lease_expired')))
             AS unresolved_attempts,
          (SELECT count(*) FROM external_deliveries
           WHERE state='pending' AND destination_revision IS NOT NULL
             AND ((sink='umami' AND destination_revision<>:umami_revision)
               OR (sink='telegram_support' AND destination_revision<>:support_revision)))
             AS pending_other_revision,
          ((SELECT count(*) FROM external_delivery_sources WHERE materialized_at IS NULL
            AND source_kind='support_case' AND mode='live' AND captured_at<:cutoff)
           +(SELECT count(*) FROM external_deliveries d
             JOIN external_delivery_sources s ON s.id=d.source_id
             WHERE d.sink='telegram_support' AND d.state IN ('pending','retry','leased')
               AND s.captured_at<:cutoff)) AS old_support_notices,
          (SELECT count(*) FROM external_delivery_sources WHERE materialized_at IS NULL)
            AS pending_sources
    """),
                {
                    "umami_revision": targets.umami.revision,
                    "support_revision": targets.telegram_support.revision,
                    "cutoff": targets.support_notice_not_before,
                },
            )
        )
        .mappings()
        .one()
    )
    return Snapshot(
        **dict(counts),
        registered=registered,
        schedules=tuple(
            Schedule(
                sink=sink_name(row.sink),
                turn=row.turn,
                blocked=row.blocked_reason is not None,
                cooldown_until=row.cooldown_until,
            )
            for row in schedules
        ),
        capture_triggers_verified=await capture_triggers_verified(session),
    )


async def register_plan(session: AsyncSession, plan: Plan) -> Snapshot:
    """Called only after the CLI's same-transaction database/head guard."""
    current = await read_snapshot(session, plan.targets)
    validate_plan(plan, current.captured_at)
    require_snapshot(plan.targets, current, registered=False)
    if any(
        before == "matching" and after != "matching"
        for before, after in zip(
            target_states(plan.targets, plan.snapshot),
            target_states(plan.targets, current),
            strict=True,
        )
    ):
        raise ActivationRejectedError("registered_target_disappeared")
    await register_transaction_destinations(session, registrations(plan.targets))
    final = await read_snapshot(session, plan.targets)
    require_snapshot(plan.targets, final, registered=True)
    return final


def read_model(path: Path, model: type[Targets] | type[Plan]) -> Targets | Plan:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o077
            or metadata.st_uid not in {0, os.geteuid()}
        ):
            raise ActivationRejectedError("unsafe_input_file")
        raw = os.read(descriptor, MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ActivationRejectedError("input_too_large")
        return model.model_validate_json(raw)
    finally:
        os.close(descriptor)


async def run(
    command: Literal["plan", "register", "check"], value: Targets | Plan
) -> dict[str, object]:
    url = os.environ.get("DATABASE_URL", "")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or parsed.database != "peerly_staging":
        raise ActivationRejectedError("wrong_database_configuration")
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
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            if command != "register":
                await session.execute(text("SET TRANSACTION READ ONLY"))
            await guard_database(session)
            if command == "register":
                if not isinstance(value, Plan):
                    raise ActivationRejectedError("approved_plan_required")
                targets, snapshot = value.targets, await register_plan(session, value)
                result: dict[str, object] = {"status": "targets_registered"}
            else:
                if not isinstance(value, Targets):
                    raise ActivationRejectedError("targets_manifest_required")
                targets = value
                snapshot = await read_snapshot(session, targets)
                require_snapshot(targets, snapshot, registered=command == "check")
                if command == "plan":
                    plan = build_plan(targets, snapshot)
                    result = plan.model_dump(mode="json")
                else:
                    result = {"status": "metadata_checks_passed"}
            if command != "plan":
                result.update(
                    targets_sha256=targets_digest(targets),
                    snapshot=snapshot.model_dump(mode="json"),
                    activation_authorized=False,
                    credentials_verified=False,
                    provider_acceptance_verified=False,
                    worker_started=False,
                )
        return result
    finally:
        await engine.dispose()


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise ActivationRejectedError("invalid_arguments")


def main() -> int:
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("command", choices=("plan", "register", "check"))
        parser.add_argument("--input", type=Path, required=True)
        args = parser.parse_args()
        model = Plan if args.command == "register" else Targets
        result = asyncio.run(run(args.command, read_model(args.input, model)))
    except ActivationRejectedError as error:
        result = {"status": "rejected", "code": error.code}
        code = 1
    except (ValueError, OSError, SQLAlchemyError, TimeoutError):
        result = {
            "status": "unconfirmed",
            "code": "invalid_input_or_storage_unavailable",
            "recovery": "Check fresh actual registry for the SAME approved targets before retry",
        }
        code = 1
    else:
        code = 0
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
