import asyncio
import hashlib
import platform
import tracemalloc
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.application.ai.ports import AiUnavailableError
from studymate.application.ai.worker import ExecuteNextJob
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.bootstrap import create_ai_admission_engine
from studymate.domain.ai.jobs import AiJob, Failure, JobState
from studymate.domain.ai.tasks import AiResult, AiTask, ClarifiedGoal, Source
from studymate.infrastructure.ai.models import AiJobRecord
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.persistence.goal_models import GoalRecord, GoalRevisionRecord
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from tests.integration.ai.test_queue import Services, goal, services, submission
from tests.integration.http_identity import BrowserHarness, verified
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration
SIMULATED_ACCOUNTS = 500
INTERACTIVE_QUEUE_CAPACITY = 90
ADMISSION_CONNECTIONS = 2
WORKER_CONNECTIONS = 1
AI_CONNECTIONS = ADMISSION_CONNECTIONS + WORKER_CONNECTIONS
MAX_PEAK_BYTES = 64 * 1024 * 1024
CORE_LATENCY_LIMIT_SECONDS = 2
ADMISSION_OBSERVED_LIMIT_SECONDS = 3


async def synthetic_accounts(engine: AsyncEngine) -> tuple[tuple[Actor, Source], ...]:
    at = datetime.now(UTC)
    actors = tuple(
        (Actor(uuid4(), SessionCredential(uuid4().hex + uuid4().hex[:11])), Source(uuid4(), 1))
        for _ in range(SIMULATED_ACCOUNTS)
    )
    async with async_sessionmaker(engine).begin() as session:
        session.add_all(AccountRecord(id=owner.id, created_at=at) for owner, _ in actors)
        await session.flush()
        session.add_all(
            InstitutionalBindingRecord(
                account_id=owner.id,
                email=f"synthetic-{owner.id.hex}@mail.apu.edu.my",
                verified_at=at,
            )
            for owner, _ in actors
        )
        session.add_all(
            SessionRecord(
                id=uuid4(),
                account_id=owner.id,
                secret_digest=hashlib.sha256(owner.credential.value.encode()).digest(),
                issued_at=at,
                expires_at=at + timedelta(days=1),
            )
            for owner, _ in actors
        )
        session.add_all(
            GoalRecord(id=source.id, account_id=owner.id, current_version=1, created_at=at)
            for owner, source in actors
        )
        await session.flush()
        session.add_all(
            GoalRevisionRecord(
                goal_id=source.id,
                account_id=owner.id,
                version=1,
                subject_label="Synthetic saturation subject",
                shared_learning=False,
                saved_at=at,
            )
            for owner, source in actors
        )
    return actors


@dataclass(slots=True)
class SlowExecutor:
    started: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    active: int = 0
    maximum_active: int = 0
    invocations: int = 0

    async def execute(self, task: AiTask, budget_seconds: float) -> AiResult:
        assert task.source.version == 1
        assert budget_seconds > 0
        self.invocations += 1
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.started.set()
        try:
            await self.release.wait()
            return ClarifiedGoal("Synthetic bounded advice")
        finally:
            self.active -= 1


@dataclass(frozen=True, slots=True)
class LoadObservation:
    accepted: int
    rejected: int
    peak: int
    core_max: float
    core_p95: float
    core_samples: int
    admission_max: float
    admission_p95: float
    connections: int

    def verify(self, record: Callable[[str, object], None]) -> None:
        # Under a simultaneous burst the bounded request deadline can reject all
        # arrivals. Positive admission/recovery are mandatory separate controls.
        assert 0 <= self.accepted <= INTERACTIVE_QUEUE_CAPACITY
        assert self.rejected > 0
        assert self.peak < MAX_PEAK_BYTES
        assert self.core_max < CORE_LATENCY_LIMIT_SECONDS
        assert self.connections <= AI_CONNECTIONS
        assert self.admission_max < ADMISSION_OBSERVED_LIMIT_SECONDS
        record("accounts", SIMULATED_ACCOUNTS)
        record("queued", self.accepted)
        record("rejected", self.rejected)
        record("peak_bytes", self.peak)
        record("core_max_seconds", self.core_max)
        record("core_p95_seconds", self.core_p95)
        record("core_samples", self.core_samples)
        record("observed_ai_checkouts", self.connections)
        record("admission_max_seconds", self.admission_max)
        record("admission_p95_seconds", self.admission_p95)


async def core_reads(
    browser: BrowserHarness, pools: tuple[AsyncAdaptedQueuePool, ...], latencies: list[float]
) -> int:
    maximum_connections = 0
    for _ in range(12):
        for route in ("/api/v1/me", "/api/v1/me/profile", "/api/ready"):
            started = perf_counter()
            response = await browser.client.get(route)
            latencies.append(perf_counter() - started)
            maximum_connections = max(maximum_connections, sum(pool.checkedout() for pool in pools))
            assert response.status_code == HTTPStatus.OK
    return maximum_connections


def percentile95(values: list[float]) -> float:
    return sorted(values)[int(0.95 * (len(values) - 1))]


async def burst(
    accounts: tuple[tuple[Actor, Source], ...],
    api: Services,
    browser: BrowserHarness,
    pools: tuple[AsyncAdaptedQueuePool, ...],
) -> LoadObservation:
    latencies: list[float] = []
    admission_latencies: list[float] = []
    maximum_connections = 0

    async def submit(item: tuple[Actor, Source]) -> bool:
        owner, source = item
        started = perf_counter()
        try:
            accepted = await api.submit(
                owner.credential, submission(source), IntentKey(str(uuid4()))
            )
            assert isinstance(accepted, AiJob)
        except AiUnavailableError:
            return False
        finally:
            admission_latencies.append(perf_counter() - started)
        return True

    async def core_traffic() -> None:
        nonlocal maximum_connections
        maximum_connections = await core_reads(browser, pools, latencies)

    tracemalloc.start()
    try:
        async with asyncio.timeout(40):
            async with asyncio.TaskGroup() as group:
                submissions = [group.create_task(submit(item)) for item in accounts[1:]]
                group.create_task(core_traffic())
            outcomes = [task.result() for task in submissions]
        _, peak = tracemalloc.get_traced_memory()
        return LoadObservation(
            sum(outcomes),
            len(outcomes) - sum(outcomes),
            peak,
            max(latencies),
            percentile95(latencies),
            len(latencies),
            max(admission_latencies),
            percentile95(admission_latencies),
            maximum_connections,
        )
    finally:
        tracemalloc.stop()


async def verify_post_burst_recovery(
    api: Services,
    account: tuple[Actor, Source],
    queued_control: AiJob,
    observation: LoadObservation,
    record_property: Callable[[str, object], None],
) -> None:
    owner, source = account
    cancelled = await api.cancel(owner.credential, queued_control.id)
    assert cancelled.state == JobState.CANCELLED
    recovered = await api.submit(
        owner.credential,
        submission(source, "Synthetic post-burst recovery control"),
        IntentKey(str(uuid4())),
    )
    assert recovered.state == JobState.QUEUED
    # Truthful degradation: only returned admissions exist, cancellation is
    # retained, and capacity recovers with the original short SQL budgets.
    async with api.sessions() as session:
        stored = tuple(await session.scalars(select(AiJobRecord)))
    assert len(stored) == observation.accepted + 3
    queued = tuple(job for job in stored if job.state == JobState.QUEUED.value)
    assert len(queued) == observation.accepted + 1
    assert len(queued) <= INTERACTIVE_QUEUE_CAPACITY
    assert next(job for job in stored if job.id == queued_control.id).state == "cancelled"
    record_property("burst_submission_attempts", SIMULATED_ACCOUNTS - 1)
    record_property("positive_control_admissions", 3)
    record_property("post_burst_recovery_admitted", True)


async def record_environment(engine: AsyncEngine, record: Callable[[str, object], None]) -> None:
    record("python", platform.python_version())
    record("platform", platform.system() + " " + platform.machine())
    async with engine.connect() as connection:
        server_version = (
            await connection.scalars(select(cast(func.current_setting("server_version"), String)))
        ).one()
    record("postgresql", server_version)


async def test_500_accounts_slow_executor_preserves_core_http_and_bounded_resources(
    ai_engine: AsyncEngine,
    database_url: str,
    browser: BrowserHarness,
    record_property: Callable[[str, object], None],
) -> None:
    await verified(browser, ai_engine)
    accounts = await synthetic_accounts(ai_engine)
    async with ai_engine.connect() as connection:
        schema = (await connection.scalars(select(cast(func.current_schema(), String)))).one()
    engine = create_ai_admission_engine(database_url, server_settings={"search_path": schema})
    worker_engine = create_async_engine(
        database_url,
        pool_size=WORKER_CONNECTIONS,
        max_overflow=0,
        connect_args={"server_settings": {"search_path": schema}},
    )
    worker_queue = SqlAiQueue(async_sessionmaker(worker_engine, expire_on_commit=False))
    api = services(engine)
    fake = SlowExecutor()
    operation: asyncio.Task[bool] | None = None
    pool, worker_pool = engine.pool, worker_engine.pool
    assert isinstance(pool, AsyncAdaptedQueuePool)
    assert isinstance(worker_pool, AsyncAdaptedQueuePool)
    pools = (pool, worker_pool)
    try:
        baseline: list[float] = []
        await core_reads(browser, pools, baseline)
        record_property("baseline_core_p95_seconds", percentile95(baseline))
        await record_environment(ai_engine, record_property)
        owner, source = accounts[0]
        await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
        operation = asyncio.create_task(ExecuteNextJob(worker_queue, fake)())
        await asyncio.wait_for(fake.started.wait(), timeout=2)
        assert worker_pool.checkedout() == 0  # No connection is held by inference.
        assert not await ExecuteNextJob(worker_queue, SlowExecutor())()
        # A queued control reserves a known cancellable slot even if the burst
        # fills every remaining interactive slot. No production budget is changed.
        queued_control = await api.submit(
            owner.credential,
            submission(source, "Synthetic queued control"),
            IntentKey(str(uuid4())),
        )
        assert queued_control.state == JobState.QUEUED
        observation = await burst(accounts, api, browser, pools)
        observation.verify(record_property)
        await verify_post_burst_recovery(
            api, accounts[0], queued_control, observation, record_property
        )
        assert fake.maximum_active == 1
        assert fake.invocations == 1
        fake.release.set()
        assert await operation
        assert pool.checkedout() == 0
        assert worker_pool.checkedout() == 0
        assert pool.size() == ADMISSION_CONNECTIONS
        assert worker_pool.size() == WORKER_CONNECTIONS
        record_property("admission_pool_size", pool.size())
        record_property("worker_pool_size", worker_pool.size())
        record_property("maximum_active", fake.maximum_active)

    finally:
        fake.release.set()
        if operation is not None and not operation.done():
            operation.cancel()
            with suppress(asyncio.CancelledError):
                await operation
        await worker_engine.dispose()
        await engine.dispose()


@dataclass(slots=True)
class HeartbeatQueue:
    queue: SqlAiQueue
    observed: asyncio.Event = field(default_factory=asyncio.Event)
    ticks: int = 0

    async def claim(self) -> AiJob | None:
        return await self.queue.claim()

    async def heartbeat(self, job: AiJob) -> bool:
        result = await self.queue.heartbeat(job)
        self.ticks += 1
        self.observed.set()
        return result

    async def complete(
        self,
        job: AiJob,
        result: AiResult | Failure,
        *,
        stopped: bool,
        retry_after: timedelta = timedelta(seconds=2),
    ) -> AiJob:
        return await self.queue.complete(job, result, stopped=stopped, retry_after=retry_after)


async def test_exhausted_admission_pool_has_short_deadline_and_does_not_starve_ten_second_heartbeat(
    ai_engine: AsyncEngine,
    database_url: str,
    browser: BrowserHarness,
) -> None:
    await verified(browser, ai_engine)
    owner = await actor(ai_engine)
    source = await goal(ai_engine, owner)
    async with ai_engine.connect() as connection:
        schema = (await connection.scalars(select(cast(func.current_schema(), String)))).one()
    admission = create_ai_admission_engine(database_url, server_settings={"search_path": schema})
    worker = create_async_engine(
        database_url,
        pool_size=WORKER_CONNECTIONS,
        max_overflow=0,
        connect_args={"server_settings": {"search_path": schema}},
    )
    api = services(admission)
    queue = HeartbeatQueue(SqlAiQueue(async_sessionmaker(worker, expire_on_commit=False)))
    fake = SlowExecutor()
    operation: asyncio.Task[bool] | None = None
    try:
        accepted = await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
        operation = asyncio.create_task(
            ExecuteNextJob(queue, fake)()
        )  # Real fixed ten-second heartbeat.
        await asyncio.wait_for(fake.started.wait(), timeout=2)
        started = perf_counter()
        async with admission.connect(), admission.connect():
            with pytest.raises(AiUnavailableError):
                await api.submit(
                    owner.credential,
                    submission(source, "Rejected before DB acquire"),
                    IntentKey(str(uuid4())),
                )
            assert perf_counter() - started < ADMISSION_OBSERVED_LIMIT_SECONDS
            async with asyncio.timeout(12):
                await queue.observed.wait()
            assert queue.ticks >= 1
            response = await browser.client.get("/api/ready")
            assert response.status_code == HTTPStatus.OK
            assert (await queue.queue.snapshot()).occupied
        fake.release.set()
        assert await operation
        async with async_sessionmaker(admission)() as session:
            stored = tuple(await session.scalars(select(AiJobRecord.id)))
            assert stored == (accepted.id,)
    finally:
        fake.release.set()
        if operation is not None and not operation.done():
            operation.cancel()
            with suppress(asyncio.CancelledError):
                await operation
        await worker.dispose()
        await admission.dispose()
