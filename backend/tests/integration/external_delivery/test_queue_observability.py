"""Real migrated PostgreSQL counts/locks/pool1, without provider calls or schema edits."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from opentelemetry.metrics import CallbackOptions
from opentelemetry.sdk.metrics import MeterProvider
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.application.external_delivery.routing import MaterializeDeliverySources
from studymate.application.external_delivery.worker import DeliverNextExternalEvent
from studymate.domain.external_delivery.delivery import (
    DeliveryLease,
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
    DeliveryScheduleRecord,
    DeliverySourceRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.external_delivery.queue import SqlExternalDeliveryQueue
from studymate.infrastructure.observability.delivery_queue import (
    DeliveryQueueSignals,
    SqlDeliveryQueueReader,
)
from studymate.infrastructure.support.models import SupportCaseRecord, SupportProofRecord

pytestmark = pytest.mark.integration
AGED_DELIVERY_SECONDS = 60
AGED_SOURCE_SECONDS = 30


async def pool_one(engine: AsyncEngine) -> AsyncEngine:
    async with engine.connect() as connection:
        schema = await connection.scalar(text("SELECT current_schema()"))
    if not isinstance(schema, str) or not schema.startswith("test_"):
        raise ValueError("Migrated disposable schema required")
    return create_async_engine(
        engine.url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
        connect_args={"server_settings": {"search_path": schema}},
    )


async def cases(engine: AsyncEngine, count: int) -> None:
    async with async_sessionmaker(engine).begin() as session:
        at = await database_now(session)
        proof = uuid4().bytes * 2
        session.add(
            SupportProofRecord(
                digest=proof, source_digest=proof, created_at=at, expires_at=at + timedelta(hours=1)
            )
        )
        await session.flush()
        session.add_all(
            SupportCaseRecord(
                id=uuid4(),
                proof_digest=proof,
                actor_id=None,
                topic="other",
                reply_address="synthetic@example.test",
                message="PRIVATE_CASE_SENTINEL",
                details=None,
                received_at=at,
            )
            for _ in range(count)
        )


async def registered(engine: AsyncEngine) -> SqlExternalDeliveryQueue:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await register_destinations(
        sessions,
        tuple(DestinationRegistration(DestinationRef(sink, 1), b"x" * 32) for sink in Sink),
    )
    return SqlExternalDeliveryQueue(sessions)


async def test_exact_delivery_and_unmaterialized_source_backlog_and_reason_recovery(
    identity_engine: AsyncEngine,
) -> None:
    engine = await pool_one(identity_engine)
    meter = MeterProvider(shutdown_on_exit=False)
    signals = DeliveryQueueSignals(meter.get_meter("synthetic"))
    try:
        queue = await registered(engine)
        await cases(identity_engine, 3)
        await MaterializeDeliverySources(SqlMaterializationUnitOfWork(queue.sessions))()
        for sink in Sink:
            target = DestinationRef(sink, 1)
            first = await queue.claim(target, 30)
            assert first is not None
            await queue.finish(
                first,
                DeliveryResult(ResultKind.RETRYABLE, FailureCode.TRANSIENT, retry_after_seconds=60),
            )
            second = await queue.claim(target, 30)
            assert second is not None
            await queue.finish(
                second,
                DeliveryResult(
                    ResultKind.PERMANENT,
                    FailureCode.CREDENTIALS if sink == Sink.UMAMI else FailureCode.PERMANENT,
                ),
            )
        await cases(identity_engine, 1)
        async with queue.sessions.begin() as session:
            at = await database_now(session)
            await session.execute(
                update(ExternalDeliveryRecord)
                .where(ExternalDeliveryRecord.state == "pending")
                .values(next_attempt_at=at - timedelta(seconds=AGED_DELIVERY_SECONDS))
            )
            await session.execute(
                update(DeliverySourceRecord)
                .where(DeliverySourceRecord.materialized_at.is_(None))
                .values(captured_at=at - timedelta(seconds=AGED_SOURCE_SECONDS))
            )
        reader = SqlDeliveryQueueReader(queue.sessions)
        observed = await reader.snapshot()
        for item in observed.sinks:
            assert (item.pending, item.retry, item.dead) == (1, 1, 1)
            assert item.oldest_due_seconds >= AGED_DELIVERY_SECONDS
        assert observed.sources_pending == 1
        assert observed.sources_oldest_seconds >= AGED_SOURCE_SECONDS
        assert await signals.sample(reader)
        assert "PRIVATE_CASE_SENTINEL" not in repr(signals.depth(CallbackOptions()))
        assert any(point.value == 1 for point in signals.blocked(CallbackOptions()))
        async with queue.sessions.begin() as session:
            await session.execute(update(DeliveryScheduleRecord).values(blocked_reason=None))
        assert await signals.sample(reader)
        assert all(point.value == 0 for point in signals.blocked(CallbackOptions()))
        await MaterializeDeliverySources(SqlMaterializationUnitOfWork(queue.sessions))()
        assert (await reader.snapshot()).sources_pending == 0
    finally:
        signals.close()
        meter.shutdown()
        await engine.dispose()


async def test_pool_acquire_and_real_table_lock_timeout_return_unknown_then_recover(
    identity_engine: AsyncEngine,
) -> None:
    engine = await pool_one(identity_engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    meter = MeterProvider(shutdown_on_exit=False)
    signals = DeliveryQueueSignals(meter.get_meter("synthetic"))
    reader = SqlDeliveryQueueReader(sessions)
    try:
        async with sessions.begin() as held:
            baseline = await held.scalar(text("SHOW statement_timeout"))
            assert not await asyncio.wait_for(signals.sample(reader), timeout=2)
        assert isinstance(engine.pool, AsyncAdaptedQueuePool)
        assert engine.pool.checkedout() == 0
        async with async_sessionmaker(identity_engine).begin() as held:
            await held.execute(text("LOCK TABLE external_deliveries IN ACCESS EXCLUSIVE MODE"))
            assert not await asyncio.wait_for(signals.sample(reader), timeout=2)
        assert signals.depth(CallbackOptions()) == ()
        assert engine.pool.checkedout() == 0
        async with sessions.begin() as session:
            assert await session.scalar(text("SHOW statement_timeout")) == baseline
            assert await session.scalar(select(DeliveryScheduleRecord.sink).limit(1)) is not None
        assert await signals.sample(reader)
        assert all(point.value == 0 for point in signals.depth(CallbackOptions()))
    finally:
        signals.close()
        meter.shutdown()
        await engine.dispose()


async def test_same_pool_one_can_sample_while_provider_port_is_waiting_outside_transaction(
    identity_engine: AsyncEngine,
) -> None:
    engine = await pool_one(identity_engine)
    meter = MeterProvider(shutdown_on_exit=False)
    signals = DeliveryQueueSignals(meter.get_meter("synthetic"))
    entered, release = asyncio.Event(), asyncio.Event()

    class Registry:
        def destination(self, sink: Sink) -> DestinationRef | None:
            return DestinationRef(sink, 1) if sink == Sink.UMAMI else None

    class Sender:
        async def send(self, _lease: DeliveryLease) -> DeliveryResult:
            entered.set()
            await release.wait()
            return DeliveryResult(ResultKind.ACCEPTED, http_status=200)

    task: asyncio.Task[bool] | None = None
    try:
        queue = await registered(engine)
        await cases(identity_engine, 1)
        await MaterializeDeliverySources(SqlMaterializationUnitOfWork(queue.sessions))()
        task = asyncio.create_task(DeliverNextExternalEvent(queue, Registry(), Sender())())
        await asyncio.wait_for(entered.wait(), timeout=2)
        assert await signals.sample(SqlDeliveryQueueReader(queue.sessions))
        async with queue.sessions.begin() as session:
            assert await session.scalar(text("SELECT 1")) == 1
        release.set()
        assert await task
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        signals.close()
        meter.shutdown()
        await engine.dispose()
