"""Real migrated schemas: blocked-sink CAS preserves retained delivery history."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.external_delivery.recovery import (
    RecoveryRejectedError,
    UmamiRecoveryState,
    UmamiRecoveryTarget,
    recover_umami_sink,
)
from studymate.application.external_delivery.routing import MaterializeDeliverySources
from studymate.domain.external_delivery.delivery import (
    DeliveryResult,
    DestinationRef,
    FailureCode,
    ResultKind,
)
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.external_delivery.destinations import (
    DestinationRegistration,
    register_destinations,
)
from studymate.infrastructure.external_delivery.materialization import (
    SqlMaterializationUnitOfWork,
    database_now,
)
from studymate.infrastructure.external_delivery.models import (
    DeliveryAttemptRecord,
    DeliveryDestinationRecord,
    DeliveryScheduleRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.external_delivery.queue import SqlExternalDeliveryQueue
from studymate.infrastructure.external_delivery.recovery import SqlUmamiRecoveryTransaction
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
SOURCE_COUNT = 2


async def blocked(engine: AsyncEngine) -> tuple[UmamiRecoveryTarget, UmamiRecoveryState]:
    owner = await actor(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        for _ in range(SOURCE_COUNT):
            session.add(
                ProductEventRecord(
                    id=uuid4(),
                    account_id=owner.id,
                    kind="auth.email_confirmed",
                    occurrence_key=f"smv1:{uuid4().hex}:p:operator",
                    schema_version=1,
                    occurred_at=await database_now(session),
                )
            )
    assert (
        await MaterializeDeliverySources(SqlMaterializationUnitOfWork(sessions))() == SOURCE_COUNT
    )
    destination = DestinationRef(Sink.UMAMI, 1)
    await register_destinations(sessions, (DestinationRegistration(destination, b"a" * 32),))
    queue = SqlExternalDeliveryQueue(sessions)
    lease = await queue.claim(destination, 30)
    assert lease is not None
    await queue.finish(lease, DeliveryResult(ResultKind.PERMANENT, FailureCode.DESTINATION, 200))
    target = UmamiRecoveryTarget(1, b"a" * 32, lease.delivery_id)
    async with sessions.begin() as session:
        snapshot = await SqlUmamiRecoveryTransaction(session).inspect(target, lock=False)
    return target, snapshot


async def history(session: AsyncSession) -> tuple[tuple[tuple[object, ...], ...], ...]:
    return (
        tuple(
            tuple(row)
            for row in (await session.execute(select(ExternalDeliveryRecord.__table__))).all()
        ),
        tuple(
            tuple(row)
            for row in (await session.execute(select(DeliveryAttemptRecord.__table__))).all()
        ),
        tuple(
            tuple(row)
            for row in (await session.execute(select(DeliveryDestinationRecord.__table__))).all()
        ),
    )


async def test_only_block_changes_dead_history_retained_and_pending_normal_claim_resumes(
    identity_engine: AsyncEngine,
) -> None:
    target, snapshot = await blocked(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions() as session:
        before = await history(session)
    async with sessions.begin() as session:
        await recover_umami_sink(SqlUmamiRecoveryTransaction(session), target, snapshot)
    async with sessions() as session:
        assert await history(session) == before
        schedule = await session.get(DeliveryScheduleRecord, "umami")
        assert schedule is not None
        assert schedule.blocked_reason is None
        assert (schedule.turn, schedule.next_claim_at, schedule.cooldown_until) == (
            snapshot.turn,
            snapshot.next_claim_at,
            snapshot.cooldown_until,
        )
    with pytest.raises(RecoveryRejectedError, match="snapshot_changed"):
        async with sessions.begin() as session:
            await recover_umami_sink(SqlUmamiRecoveryTransaction(session), target, snapshot)
    # No recovery-created attempt; the ordinary queue alone may claim a pending delivery.
    next_lease = await SqlExternalDeliveryQueue(sessions).claim(DestinationRef(Sink.UMAMI, 1), 30)
    assert next_lease is not None
    assert next_lease.delivery_id != target.failed_delivery_id
    assert next_lease.attempt_no == 1


async def test_rollback_restores_block_and_changed_registry_or_schedule_rejects(
    identity_engine: AsyncEngine,
) -> None:
    target, snapshot = await blocked(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)

    async def rollback() -> None:
        async with sessions.begin() as session:
            await recover_umami_sink(SqlUmamiRecoveryTransaction(session), target, snapshot)
            raise RuntimeError("rollback")

    with pytest.raises(RuntimeError, match="rollback"):
        await rollback()
    async with sessions.begin() as session:
        assert (
            await SqlUmamiRecoveryTransaction(session).inspect(target, lock=False)
        ).blocked_reason == "destination_unavailable"
        await session.execute(
            update(DeliveryScheduleRecord)
            .where(DeliveryScheduleRecord.sink == "umami")
            .values(next_claim_at=snapshot.next_claim_at + timedelta(seconds=1))
        )
    with pytest.raises(RecoveryRejectedError, match="snapshot_changed"):
        async with sessions.begin() as session:
            await recover_umami_sink(SqlUmamiRecoveryTransaction(session), target, snapshot)
    with pytest.raises(RecoveryRejectedError, match="registry_target"):
        async with sessions.begin() as session:
            await SqlUmamiRecoveryTransaction(session).inspect(
                replace(target, fingerprint=b"b" * 32), lock=True
            )


async def test_new_registry_revision_and_nonmatching_failure_fail_closed(
    identity_engine: AsyncEngine,
) -> None:
    target, snapshot = await blocked(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    await register_destinations(
        sessions, (DestinationRegistration(DestinationRef(Sink.UMAMI, 2), b"b" * 32),)
    )
    with pytest.raises(RecoveryRejectedError, match="registry_target"):
        async with sessions.begin() as session:
            await recover_umami_sink(SqlUmamiRecoveryTransaction(session), target, snapshot)
    async with sessions() as session:
        schedule = await session.get(DeliveryScheduleRecord, "umami")
        assert schedule is not None
        assert schedule.blocked_reason == "destination_unavailable"
