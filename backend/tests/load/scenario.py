"""Explicitly invoked scenarios; not collected by the ordinary test filename pattern."""

import asyncio
import hashlib
import json
import os
import platform
import resource
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

import studymate.bootstrap as actual_bootstrap
import studymate.infrastructure.ai.persistence as actual_ai_persistence
from studymate.application.ai.worker import ExecuteNextJob
from studymate.domain.ai.jobs import JobState
from studymate.infrastructure.ai.models import AiJobRecord, AiSlotRecord
from studymate.infrastructure.ai.persistence import SqlAiTransaction
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.ai.runtime.availability import (
    RUNTIME_HEARTBEAT_SECONDS,
    require_runtime_ready,
)
from studymate.infrastructure.ai.runtime.health import SqlRuntimeHealth
from tests.integration.ai.runtime.facts import fake_runtime_ready
from tests.integration.ai.test_queue import VERSIONS
from tests.integration.ai.test_saturation import (
    ADMISSION_CONNECTIONS,
    INTERACTIVE_QUEUE_CAPACITY,
    SlowExecutor,
    record_environment,
)
from tests.integration.http_identity import BrowserHarness, verified
from tests.load.harness import (
    Accepted,
    Student,
    accepted,
    cancel,
    mixed_http,
    reconcile,
    replay,
    security_controls,
    students,
)
from tests.load.measurements import LoadPlan, Mode

pytestmark = pytest.mark.integration
SCENARIO_SECONDS = 90


@asynccontextmanager
async def worker_engine(browser: BrowserHarness, database_url: str) -> AsyncIterator[AsyncEngine]:
    async with browser.ai_engine.connect() as connection:
        schema: object = (await connection.exec_driver_sql("SELECT current_schema()")).scalar_one()
    assert isinstance(schema, str)
    assert schema.startswith("test_")
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
        connect_args={
            "timeout": 5,
            "server_settings": {"search_path": schema, "lock_timeout": "1000"},
        },
    )
    try:
        yield engine
    finally:
        await engine.dispose()


async def fresh_runtime(health: SqlRuntimeHealth) -> tuple[datetime, datetime]:
    async with health.sessions() as session:
        slot = await session.get(AiSlotRecord, 1)
        assert slot is not None
        at = await SqlAiTransaction(session).now()
        assert require_runtime_ready(slot, at, VERSIONS, worker_id=health.worker_id) == VERSIONS
        assert slot.runtime_heartbeat_at is not None
        return slot.runtime_heartbeat_at, at


async def slow_traffic(
    browser: BrowserHarness,
    population: tuple[Student, ...],
    plan: LoadPlan,
    health: SqlRuntimeHealth,
    executor: SlowExecutor,
) -> dict[str, object]:
    heartbeat_before, clock_before = await fresh_runtime(health)
    observation = await mixed_http(browser, population, plan)
    heartbeat_after, clock_after = await fresh_runtime(health)
    assert heartbeat_after >= heartbeat_before
    if observation.elapsed >= RUNTIME_HEARTBEAT_SECONDS:
        assert heartbeat_after > heartbeat_before
    assert executor.active == 1
    receipt = observation.receipt(plan)
    receipt.update(
        {
            "runtime_ready_before_traffic": True,
            "runtime_ready_after_traffic": True,
            "runtime_heartbeat_before": heartbeat_before.isoformat(),
            "runtime_heartbeat_after": heartbeat_after.isoformat(),
            "runtime_clock_before": clock_before.isoformat(),
            "runtime_clock_after": clock_after.isoformat(),
            "runtime_heartbeat_advanced_during_traffic": heartbeat_after > heartbeat_before,
            "executor_active_after_traffic": True,
            "runtime_health_pool": "worker",
        }
    )
    return receipt


async def slow_scenario(
    browser: BrowserHarness, population: tuple[Student, ...], plan: LoadPlan, worker: AsyncEngine
) -> dict[str, object]:
    sessions = async_sessionmaker(browser.ai_engine, expire_on_commit=False)
    executor = SlowExecutor()
    queue = SqlAiQueue(async_sessionmaker(worker, expire_on_commit=False))
    commands: list[Accepted] = []
    operation: asyncio.Task[bool] | None = None
    # Production runtime factory shares its dedicated worker pool between queue
    # and readiness heartbeat, never the bounded HTTP admission pool.
    async with fake_runtime_ready(worker, VERSIONS) as health:
        assert worker is not browser.ai_engine
        assert health.sessions.kw["bind"] is worker
        try:
            commands.append(await accepted(browser, population[0], "running-control"))
            await security_controls(browser, commands[0], population[1])
            operation = asyncio.create_task(ExecuteNextJob(queue, executor)())
            await asyncio.wait_for(executor.started.wait(), timeout=2)
            pool = worker.pool
            assert isinstance(pool, AsyncAdaptedQueuePool)
            assert pool.checkedout() == 0
            # Deliberate finite saturation setup through actual authenticated HTTP,
            # outside measurement. No direct queued-row inserts or budget uplift.
            commands.extend(
                [
                    await accepted(browser, student, "queue-control")
                    for student in population[1 : INTERACTIVE_QUEUE_CAPACITY + 1]
                ]
            )
            async with sessions() as session:
                queued = tuple(
                    await session.scalars(select(AiJobRecord).where(AiJobRecord.state == "queued"))
                )
            assert len(queued) == INTERACTIVE_QUEUE_CAPACITY
            receipt = await slow_traffic(browser, population, plan, health, executor)
            await replay(browser, commands[1])
            await cancel(browser, commands[1])
            commands.append(await accepted(browser, population[1], "recovery-control"))
            await reconcile(sessions, tuple(commands))
            assert executor.maximum_active == 1
            assert executor.invocations == 1
            assert not operation.done()
            assert pool.checkedout() == 0
            executor.release.set()
            assert await operation
            async with sessions() as session:
                completed = await session.get(AiJobRecord, commands[0].job_id)
                cancelled = await session.get(AiJobRecord, commands[1].job_id)
            assert completed is not None
            assert completed.state == JobState.SUCCEEDED.value
            assert cancelled is not None
            assert cancelled.state == JobState.CANCELLED.value
            receipt.update(
                {
                    "setup_queued": len(queued),
                    "executor_maximum_active": executor.maximum_active,
                    "positive_http_admissions": len(commands),
                    "durable_reconciled": True,
                    "cancel_and_recovery": True,
                    "worker_pool_size": pool.size(),
                }
            )
            return receipt
        finally:
            executor.release.set()
            if operation is not None and not operation.done():
                operation.cancel()
                with suppress(asyncio.CancelledError):
                    await operation


async def offline_scenario(
    browser: BrowserHarness, population: tuple[Student, ...], plan: LoadPlan, worker: AsyncEngine
) -> dict[str, object]:
    sessions = async_sessionmaker(browser.ai_engine, expire_on_commit=False)
    async with fake_runtime_ready(worker, VERSIONS):
        first = await accepted(browser, population[0], "offline-retained-control")
        await security_controls(browser, first, population[1])
    # Real health.revoke(clean=True) retired this idle synthetic worker. There is
    # no ready worker, heartbeat fabrication, inference task or provider call.
    observation = await mixed_http(browser, population, plan)
    receipt = observation.receipt(plan)
    await replay(browser, first)
    await reconcile(sessions, (first,))
    async with fake_runtime_ready(worker, VERSIONS):
        recovered = await accepted(browser, population[1], "offline-recovery-control")
    await reconcile(sessions, (first, recovered))
    receipt.update(
        {
            "executor_maximum_active": 0,
            "positive_http_admissions": 2,
            "durable_reconciled": True,
            "retained_replay_while_offline": True,
            "ready_again_recovery": True,
        }
    )
    return receipt


@pytest.mark.parametrize("mode", [Mode.SLOW, Mode.OFFLINE])
async def test_root_http_backpressure_and_core_continuity(
    browser: BrowserHarness,
    database_url: str,
    mode: Mode,
    record_property: Callable[[str, object], None],
) -> None:
    plan = LoadPlan(
        int(os.environ.get("PEERLY_LOAD_ACTIVE", "100")),
        int(os.environ.get("PEERLY_LOAD_CONCURRENCY", "10")),
        mode,
    )
    await verified(browser, browser.ai_engine)
    population = await students(browser)
    before = resource.getrusage(resource.RUSAGE_SELF)
    source_paths = {
        "bootstrap": actual_bootstrap.__file__,
        "ai_persistence": actual_ai_persistence.__file__,
        "load_scenario": __file__,
        "load_harness": str(Path(__file__).with_name("harness.py")),
        "load_measurements": str(Path(__file__).with_name("measurements.py")),
    }
    source_hashes = {
        name: hashlib.sha256(await asyncio.to_thread(Path(path).read_bytes)).hexdigest()
        for name, path in source_paths.items()
    }
    async with asyncio.timeout(SCENARIO_SECONDS), worker_engine(browser, database_url) as worker:
        receipt = (
            await slow_scenario(browser, population, plan, worker)
            if mode == Mode.SLOW
            else await offline_scenario(browser, population, plan, worker)
        )
    after = resource.getrusage(resource.RUSAGE_SELF)
    for name, path in source_paths.items():
        assert (
            hashlib.sha256(await asyncio.to_thread(Path(path).read_bytes)).hexdigest()
            == source_hashes[name]
        )
    await record_environment(browser.ai_engine, receipt.__setitem__)
    receipt["source_sha256"] = source_hashes
    receipt["negative_http_security_controls"] = 3
    receipt.update(
        {
            "mode": mode.value,
            "configuration": asdict(plan),
            "python": platform.python_version(),
            "platform": platform.system() + " " + platform.machine(),
            "cpu_count": os.cpu_count(),
            "process_peak_rss_kib": after.ru_maxrss,
            "scenario_cpu_seconds": after.ru_utime
            + after.ru_stime
            - before.ru_utime
            - before.ru_stime,
            "transport": "root-asgi-in-process",
            "provider": "controlled-no-network",
            "registration_flow_covered": False,
            "production_capacity_accepted": False,
            "rss_scope": "whole-process-high-water-includes-seeding",
            "cpu_scope": "scenario-includes-queue-setup-excludes-student-seeding",
            "host_physical_memory_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
            "sse_uploads_and_live_provider_covered": False,
        }
    )
    admission_pool = browser.ai_engine.pool
    assert isinstance(admission_pool, AsyncAdaptedQueuePool)
    assert admission_pool.checkedout() == 0
    receipt["admission_pool_size"] = admission_pool.size()
    assert admission_pool.size() == ADMISSION_CONNECTIONS
    encoded = json.dumps(receipt, sort_keys=True, allow_nan=False)
    record_property("load_receipt", encoded)
    output = os.environ.get("PEERLY_LOAD_RECEIPT_DIRECTORY")
    if output:
        await asyncio.to_thread((Path(output) / (mode.value + ".json")).write_text, encoded + "\n")
