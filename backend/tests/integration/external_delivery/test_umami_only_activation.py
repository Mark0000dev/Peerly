from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from deployment.backend.external_delivery_activation import (
    ActivationRejectedError,
    Snapshot,
    SupportTarget,
    Targets,
    UmamiOnlyTargets,
    UmamiTarget,
    build_plan,
    read_snapshot,
    register_plan,
    registrations,
    require_snapshot,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.external_delivery.routing import MaterializeDeliverySources
from studymate.application.external_delivery.worker import DeliverNextExternalEvent
from studymate.bootstrap import _ConfiguredExternalDestinations
from studymate.domain.external_delivery.delivery import DeliveryLease, DeliveryResult, ResultKind
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.external_delivery.materialization import SqlMaterializationUnitOfWork
from studymate.infrastructure.external_delivery.models import (
    DeliveryAttemptRecord,
    DeliveryDestinationRecord,
    DeliveryScheduleRecord,
    DeliverySourceRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.external_delivery.queue import SqlExternalDeliveryQueue
from tests.integration.external_delivery.test_queue_observability import cases

pytestmark = pytest.mark.integration
CASES = 2


def target() -> UmamiOnlyTargets:
    return UmamiOnlyTargets(
        schema_version=2,
        mode="umami_only",
        database="peerly_staging",
        database_schema="public",
        migration_revision="0060_report_triage",
        backend_image="ghcr.io/mark0000dev/peerly-backend@sha256:" + "a" * 64,
        umami=UmamiTarget(
            revision=1, origin="https://analytics.example.test", website_id=UUID(int=1)
        ),
    )


async def registered(engine: AsyncEngine, configured: UmamiOnlyTargets) -> Snapshot:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        plan = build_plan(configured, await read_snapshot(session, configured))
    async with sessions.begin() as session:
        return await register_plan(session, plan)


async def test_exact_one_sink_registration_replay_and_check_preserve_original_time(
    identity_engine: AsyncEngine,
) -> None:
    configured = target()
    first = await registered(identity_engine, configured)
    second = await registered(identity_engine, configured)
    assert first.registered == second.registered
    assert len(first.registered) == 1
    assert first.registered[0].sink == "umami"
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions() as session:
        checked = await read_snapshot(session, configured)
    require_snapshot(configured, checked, registered=True)
    assert checked.deferred_support is not None
    assert checked.deferred_support.registered_destinations == 0
    assert checked.old_support_notices is None


async def test_registration_writer_remains_inside_callers_atomic_transaction(
    identity_engine: AsyncEngine,
) -> None:
    configured = target()
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        plan = build_plan(configured, await read_snapshot(session, configured))

    async def rollback() -> None:
        async with sessions.begin() as session:
            await register_plan(session, plan)
            raise RuntimeError("synthetic caller rollback")

    with pytest.raises(RuntimeError, match="synthetic caller rollback"):
        await rollback()
    async with sessions() as session:
        assert tuple(await session.scalars(select(DeliveryDestinationRecord))) == ()


async def test_stale_partial_approval_never_writes_a_destination(
    identity_engine: AsyncEngine,
) -> None:
    configured = target()
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        snapshot = await read_snapshot(session, configured)
    old = snapshot.model_copy(update={"captured_at": snapshot.captured_at - timedelta(minutes=6)})
    with pytest.raises(ActivationRejectedError, match="stale_or_future"):
        async with sessions.begin() as session:
            await register_plan(session, build_plan(configured, old))
    async with sessions() as session:
        assert tuple(await session.scalars(select(DeliveryDestinationRecord))) == ()


async def test_changed_umami_target_cannot_rebind_existing_revision(
    identity_engine: AsyncEngine,
) -> None:
    configured = target()
    first = await registered(identity_engine, configured)
    changed = configured.model_copy(
        update={
            "umami": configured.umami.model_copy(update={"origin": "https://another.example.test"})
        }
    )
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        plan = build_plan(changed, await read_snapshot(session, changed))
    with pytest.raises(ActivationRejectedError, match="registered_target_mismatch"):
        async with sessions.begin() as session:
            await register_plan(session, plan)
    async with sessions() as session:
        final = await read_snapshot(session, configured)
    assert first.registered == final.registered


@dataclass(slots=True)
class UmamiBoundary:
    leases: list[DeliveryLease] = field(default_factory=list)

    async def send(self, lease: DeliveryLease) -> DeliveryResult:
        assert lease.destination.sink == Sink.UMAMI
        self.leases.append(lease)
        return DeliveryResult(ResultKind.ACCEPTED, http_status=204)


async def test_deferred_telegram_is_durable_unbound_and_never_attempted_while_umami_drains(
    identity_engine: AsyncEngine,
) -> None:
    configured = target()
    await cases(identity_engine, CASES)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    assert await MaterializeDeliverySources(SqlMaterializationUnitOfWork(sessions))() == CASES
    first = await registered(identity_engine, configured)
    assert first.deferred_support is not None
    assert first.deferred_support.pending_unbound == CASES
    assert first.deferred_support.registered_destinations == 0
    sender = UmamiBoundary()
    registry = _ConfiguredExternalDestinations(
        tuple(item.destination for item in registrations(configured))
    )
    deliver = DeliverNextExternalEvent(SqlExternalDeliveryQueue(sessions), registry, sender)
    for _ in range(CASES):
        assert await deliver()
    assert not await deliver()
    assert len(sender.leases) == CASES
    assert "PRIVATE_CASE_SENTINEL" not in repr(sender.leases)
    async with sessions() as session:
        notices = tuple(
            await session.scalars(
                select(ExternalDeliveryRecord).where(
                    ExternalDeliveryRecord.sink == "telegram_support"
                )
            )
        )
        notice_ids = tuple(row.id for row in notices)
        attempted = tuple(
            await session.scalars(
                select(DeliveryAttemptRecord).where(
                    DeliveryAttemptRecord.delivery_id.in_(notice_ids)
                )
            )
        )
        sources = tuple(await session.scalars(select(DeliverySourceRecord)))
    assert len(notices) == CASES
    assert all(
        row.state == "pending" and row.destination_revision is None and row.attempt_count == 0
        for row in notices
    )
    assert not attempted
    assert all(row.materialized_at is not None for row in sources)


def full_target(configured: UmamiOnlyTargets, cutoff: datetime) -> Targets:
    return Targets(
        schema_version=1,
        database=configured.database,
        database_schema=configured.database_schema,
        migration_revision=configured.migration_revision,
        backend_image=configured.backend_image,
        support_notice_not_before=cutoff,
        umami=configured.umami,
        telegram_support=SupportTarget(
            revision=1,
            chat_id=-100123456,
            operator_origin="https://app.example.test",
            topic_id=None,
        ),
    )


async def test_later_both_mode_preserves_umami_target_without_enabling_running_support_registry(
    identity_engine: AsyncEngine,
) -> None:
    configured = target()
    first = await registered(identity_engine, configured)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    # There is no historical support backlog to waive in this compatibility case.
    full = full_target(configured, first.captured_at - timedelta(seconds=1))
    async with sessions.begin() as session:
        plan = build_plan(full, await read_snapshot(session, full))
    async with sessions.begin() as session:
        later = await register_plan(session, plan)
    assert len(later.registered) == len(Sink)
    assert next(row for row in later.registered if row.sink == "umami") == first.registered[0]
    await cases(identity_engine, 1)
    assert await MaterializeDeliverySources(SqlMaterializationUnitOfWork(sessions))() == 1
    registry = _ConfiguredExternalDestinations(
        tuple(item.destination for item in registrations(configured))
    )
    sender = UmamiBoundary()
    deliver = DeliverNextExternalEvent(SqlExternalDeliveryQueue(sessions), registry, sender)
    assert await deliver()
    assert registry.destination(Sink.TELEGRAM_SUPPORT) is None
    assert not await deliver()
    async with sessions() as session:
        notice = (
            await session.scalars(
                select(ExternalDeliveryRecord).where(
                    ExternalDeliveryRecord.sink == "telegram_support"
                )
            )
        ).one()
    assert notice.destination_revision is None
    assert notice.attempt_count == 0


async def test_later_full_plan_cannot_silently_authorize_deferred_historical_support(
    identity_engine: AsyncEngine,
) -> None:
    configured = target()
    await cases(identity_engine, CASES)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    assert await MaterializeDeliverySources(SqlMaterializationUnitOfWork(sessions))() == CASES
    first = await registered(identity_engine, configured)
    full = full_target(configured, first.captured_at)
    async with sessions() as session:
        blocked = await read_snapshot(session, full)
    assert blocked.old_support_notices == CASES
    with pytest.raises(ActivationRejectedError, match="historical_support_requires_review"):
        async with sessions.begin() as session:
            await register_plan(session, build_plan(full, blocked))
    async with sessions() as session:
        rows = tuple(await session.scalars(select(DeliveryDestinationRecord)))
        notices = tuple(
            await session.scalars(
                select(ExternalDeliveryRecord).where(
                    ExternalDeliveryRecord.sink == "telegram_support"
                )
            )
        )
    assert len(rows) == 1
    assert rows[0].sink == "umami"
    assert len(notices) == CASES
    assert all(row.destination_revision is None and row.attempt_count == 0 for row in notices)


async def test_disabled_support_schedule_is_reported_but_does_not_gate_umami_registration(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    await cases(identity_engine, 1)
    async with sessions.begin() as session:
        await session.execute(
            update(DeliveryScheduleRecord)
            .where(DeliveryScheduleRecord.sink == "telegram_support")
            .values(blocked_reason="credentials_unavailable")
        )
    result = await registered(identity_engine, target())
    assert result.deferred_support is not None
    assert result.deferred_support.sources_pending == 1
    assert len(result.registered) == 1
    assert next(row for row in result.schedules if row.sink == "telegram_support").blocked
