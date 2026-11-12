"""Causal PG regression, explicit selection alongside the corrected scenario."""

import asyncio
from collections.abc import Callable

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy.sql.dml import Update

from studymate.infrastructure.ai.models import AiSlotRecord
from tests.integration.ai.runtime.facts import fake_runtime_ready
from tests.integration.ai.test_queue import VERSIONS
from tests.integration.http_identity import BrowserHarness
from tests.load.scenario import worker_engine

pytestmark = pytest.mark.integration


async def test_readiness_renews_on_worker_pool_while_all_admission_connections_are_held(
    browser: BrowserHarness,
    database_url: str,
) -> None:
    renewed = asyncio.Event()

    def heartbeat_sql(*, context: ExecutionContext, **_ignored: object) -> None:
        compiled = context.compiled.statement if context.compiled is not None else None
        if isinstance(compiled, Update):
            table_name: object = getattr(compiled.table, "name", None)
            if table_name == AiSlotRecord.__tablename__:
                renewed.set()

    async with worker_engine(browser, database_url) as worker:
        await observed_renewal(browser, worker, renewed, heartbeat_sql)


async def observed_renewal(
    browser: BrowserHarness,
    worker: AsyncEngine,
    renewed: asyncio.Event,
    heartbeat_sql: Callable[..., None],
) -> None:
    sessions = async_sessionmaker(worker, expire_on_commit=False)
    async with fake_runtime_ready(worker, VERSIONS):
        async with sessions() as session:
            before = (await session.scalars(select(AiSlotRecord.runtime_heartbeat_at))).one()
        event.listen(worker.sync_engine, "after_cursor_execute", heartbeat_sql, named=True)
        try:
            async with browser.ai_engine.connect(), browser.ai_engine.connect():
                admission_pool = browser.ai_engine.pool
                assert isinstance(admission_pool, AsyncAdaptedQueuePool)
                assert admission_pool.checkedout() == admission_pool.size()
                with pytest.raises(PoolTimeoutError):
                    await attempt_checkout(browser.ai_engine)
                # Await the actual existing five-second renewal task's SQL; no
                # manual heartbeat, changed interval, fake readiness or retry.
                async with asyncio.timeout(8):
                    await renewed.wait()
                    async with sessions() as session:
                        after = (
                            await session.scalars(select(AiSlotRecord.runtime_heartbeat_at))
                        ).one()
                assert before is not None
                assert after is not None
                assert after > before
        finally:
            event.remove(worker.sync_engine, "after_cursor_execute", heartbeat_sql)


async def attempt_checkout(engine: AsyncEngine) -> None:
    async with engine.connect():
        return
