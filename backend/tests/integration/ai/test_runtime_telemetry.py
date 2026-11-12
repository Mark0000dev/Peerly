"""Real PostgreSQL pool1 observations remain short and release before inference."""

import asyncio
from time import perf_counter
from uuid import uuid4

import pytest
from opentelemetry.metrics import CallbackOptions
from opentelemetry.sdk.metrics import MeterProvider
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.application.ai.worker import ExecuteNextJob
from studymate.application.idempotency import IntentKey
from studymate.infrastructure.ai.models import AiSlotRecord
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.ai.runtime.health import SqlRuntimeHealth
from studymate.infrastructure.ai.runtime.supervisor import AiWorkerSupervisor
from studymate.infrastructure.ai.telemetry import AiQueueSignals, ObservedAiQueue, ObservedAiStep
from tests.integration.ai.test_queue import VERSIONS, goal, services, submission
from tests.integration.ai.test_saturation import SlowExecutor
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
BOUND_SECONDS = 2


async def pool_one(engine: AsyncEngine) -> AsyncEngine:
    async with engine.connect() as connection:
        schema = await connection.scalar(text("select current_schema()"))
    if not isinstance(schema, str) or not schema.startswith("test_"):
        raise ValueError("Disposable migrated test schema required")
    return create_async_engine(
        engine.url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
        connect_args={"server_settings": {"search_path": schema}},
    )


async def test_sampler_cancelled_sql_and_pool_wait_leave_heartbeat_capacity(
    identity_engine: AsyncEngine,
) -> None:
    engine = await pool_one(identity_engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    queue = SqlAiQueue(sessions)
    health = SqlRuntimeHealth(sessions, uuid4(), VERSIONS)
    meter = MeterProvider(shutdown_on_exit=False)
    signals = AiQueueSignals(meter.get_meter("synthetic"))
    try:
        await health.register()
        await health.heartbeat(ready=True)
        assert isinstance(engine.pool, AsyncAdaptedQueuePool)
        # Cancellation while waiting for the single connection must not leak a waiter.
        async with sessions.begin() as held:
            await held.execute(text("select 1"))
            started = perf_counter()
            assert not await asyncio.wait_for(signals.sample(queue), timeout=2)
            assert perf_counter() - started < BOUND_SECONDS
        assert engine.pool.checkedout() == 0
        await asyncio.wait_for(health.heartbeat(), timeout=2)
        assert signals.depth(CallbackOptions()) == ()
        # Also cancel a real blocked SQL read, not just a pool-acquisition fake.
        async with async_sessionmaker(identity_engine).begin() as blocker:
            await blocker.execute(text("LOCK TABLE ai_jobs IN ACCESS EXCLUSIVE MODE"))
            assert not await asyncio.wait_for(signals.sample(queue), timeout=2)
            assert engine.pool.checkedout() == 0
            await asyncio.wait_for(health.heartbeat(), timeout=2)
        assert await signals.sample(queue)
        assert signals.latest.queued == 0
        assert engine.pool.checkedout() == 0
        await health.revoke(clean=True)
    finally:
        meter.shutdown()
        await engine.dispose()


async def test_same_supervisor_observes_actual_queue_while_inference_releases_pool_one(
    identity_engine: AsyncEngine,
) -> None:
    api = services(identity_engine)
    health = SqlRuntimeHealth(api.sessions, uuid4(), VERSIONS)
    await health.register()
    await health.heartbeat(ready=True)
    owner = await actor(identity_engine)
    source = await goal(identity_engine, owner)
    created = await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    engine = await pool_one(identity_engine)
    queue = SqlAiQueue(async_sessionmaker(engine, expire_on_commit=False))
    meter = MeterProvider(shutdown_on_exit=False)
    signals = AiQueueSignals(meter.get_meter("synthetic"))
    executor = SlowExecutor()
    completed = asyncio.Event()
    observed = ObservedAiStep(
        ExecuteNextJob(ObservedAiQueue(queue), executor, heartbeat_seconds=0.05),
        meter=meter.get_meter("synthetic"),
    )

    async def step() -> bool:
        result = await observed()
        if result:
            completed.set()
        return result

    supervisor = AiWorkerSupervisor(step)
    stop = asyncio.Event()
    worker = asyncio.create_task(supervisor.run(stop))
    sampler = asyncio.create_task(signals.run(queue, stop))
    try:
        await asyncio.wait_for(executor.started.wait(), timeout=2)
        assert isinstance(engine.pool, AsyncAdaptedQueuePool)
        assert await signals.sample(queue)
        assert signals.latest.occupied
        assert engine.pool.checkedout() == 0
        # Runtime health shares precisely this pool1; no inference-held session.
        heartbeat = SqlRuntimeHealth(queue.sessions, health.worker_id, VERSIONS)
        await asyncio.wait_for(heartbeat.heartbeat(), timeout=2)
        executor.release.set()
        await asyncio.wait_for(completed.wait(), timeout=2)
        stop.set()
        await asyncio.wait_for(worker, timeout=2)
        await sampler
        saved = await api.read(owner.credential, created.id)
        assert saved.state.value == "succeeded"
        assert engine.pool.checkedout() == 0
        await health.revoke(clean=True)
    finally:
        stop.set()
        executor.release.set()
        await asyncio.gather(worker, sampler, return_exceptions=True)
        meter.shutdown()
        await engine.dispose()


async def test_snapshot_uses_one_select_for_actual_queued_age_and_pause(
    ai_engine: AsyncEngine,
) -> None:
    api = services(ai_engine)
    owner = await actor(ai_engine)
    source = await goal(ai_engine, owner)
    await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    engine = await pool_one(ai_engine)
    reads: list[str] = []

    def observe(*arguments: object) -> None:
        statement = arguments[2]
        if isinstance(statement, str) and statement.lstrip().upper().startswith("SELECT"):
            reads.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", observe)
    try:
        queue = SqlAiQueue(async_sessionmaker(engine, expire_on_commit=False))
        initial = await queue.snapshot()
        assert initial.queued == 1
        assert initial.oldest_seconds >= 0
        assert not initial.occupied
        assert not initial.circuit_open
        assert len(reads) == 1
        async with api.sessions.begin() as session:
            await session.execute(
                update(AiSlotRecord).values(
                    paused_until=func.clock_timestamp() + text("interval '1 minute'"),
                )
            )
        assert (await queue.snapshot()).circuit_open
        async with api.sessions.begin() as session:
            await session.execute(
                update(AiSlotRecord).values(
                    paused_until=func.clock_timestamp() - text("interval '1 minute'"),
                )
            )
        assert not (await queue.snapshot()).circuit_open
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", observe)
        await engine.dispose()


async def test_snapshot_missing_singleton_preserves_empty_queue_without_extra_reads(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await session.execute(delete(AiSlotRecord))
    snapshot = await SqlAiQueue(sessions).snapshot()
    assert snapshot.queued == 0
    assert snapshot.oldest_seconds == 0
    assert not snapshot.occupied
    assert not snapshot.circuit_open
    async with sessions() as session:
        # The observer must not manufacture/recreate the missing singleton.
        assert await session.scalar(select(func.count()).select_from(AiSlotRecord)) == 0
