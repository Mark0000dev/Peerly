"""Controlled native queue with the actual report guard injected; no provider process."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.ai.runtime.health import (
    REPORT_GUARD_VERSION,
    RuntimeOwnershipError,
    SqlRuntimeHealth,
)
from studymate.infrastructure.operator.report_triage_guard import SqlReportTriageSourceGuard
from tests.integration.ai.test_queue import VERSIONS


@pytest.fixture
async def triage_queue(identity_engine: AsyncEngine) -> AsyncIterator[SqlAiQueue]:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    queue = SqlAiQueue(sessions, reports=SqlReportTriageSourceGuard(), worker_id=uuid4())
    assert queue.worker_id is not None
    health = SqlRuntimeHealth(
        sessions,
        queue.worker_id,
        VERSIONS,
        report_guard_version=REPORT_GUARD_VERSION if queue.reports is not None else None,
    )
    await health.register()
    await health.heartbeat(ready=True)
    stopping = asyncio.Event()

    async def renew() -> None:
        while not stopping.is_set():
            try:
                await asyncio.wait_for(stopping.wait(), 5)
            except TimeoutError:
                with suppress(RuntimeOwnershipError):
                    await health.heartbeat()

    task = asyncio.create_task(renew())
    try:
        yield queue
    finally:
        stopping.set()
        await task
        await health.revoke(clean=True)


@pytest.fixture
async def ai_engine(identity_engine: AsyncEngine, triage_queue: SqlAiQueue) -> AsyncEngine:
    assert triage_queue.reports is not None
    return identity_engine
