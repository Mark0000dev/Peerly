import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Literal

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.selectable import Select

from studymate.infrastructure.observability import delivery_queue as sampler
from studymate.infrastructure.persistence.transactions import open_transaction
from tests.integration.external_delivery.test_queue_observability import pool_one

pytestmark = pytest.mark.integration


async def settings(session: AsyncSession) -> tuple[str, str, str]:
    row = (
        await session.execute(
            select(
                func.current_setting("transaction_read_only"),
                func.current_setting("statement_timeout"),
                func.current_setting("lock_timeout"),
            )
        )
    ).one()
    read_only, statement, lock = row
    assert isinstance(read_only, str)
    assert isinstance(statement, str)
    assert isinstance(lock, str)
    return read_only, statement, lock


async def read_only_update(session: AsyncSession) -> None:
    async with session.begin_nested():
        # No fixture data would change if the guard were broken: PostgreSQL must
        # still reject this actual DML command before examining the false predicate.
        await session.execute(text("UPDATE external_delivery_schedule SET turn=turn WHERE false"))


type Transaction = Callable[
    [async_sessionmaker[AsyncSession]], AbstractAsyncContextManager[AsyncSession]
]


def inspected_transaction(
    original: Transaction,
    finish: Literal["commit", "rollback", "cancel"],
    entered: asyncio.Event,
) -> Transaction:
    @asynccontextmanager
    async def inspected(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
        async with original(factory) as session:
            yield session
            assert await settings(session) == ("on", "75ms", "25ms")
            with pytest.raises(DBAPIError) as rejected:
                await read_only_update(session)
            code: object = getattr(rejected.value.orig, "sqlstate", None)
            assert code == "25006"
            if finish == "rollback":
                raise RuntimeError("synthetic post-read rollback")
            if finish == "cancel":
                entered.set()
                await asyncio.Event().wait()

    return inspected


@pytest.mark.parametrize("finish", ["commit", "rollback", "cancel"])
async def test_combined_setup_is_local_read_only_and_restores_pool_on_every_exit(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    finish: Literal["commit", "rollback", "cancel"],
) -> None:
    engine = await pool_one(identity_engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    original = open_transaction
    entered = asyncio.Event()
    query_kinds: list[str] = []

    def observe(*, context: ExecutionContext, **_ignored: object) -> None:
        statement = context.compiled.statement if context.compiled is not None else None
        if isinstance(statement, Select):
            columns = tuple(statement.selected_columns)
            if columns and all(
                isinstance(column, Function) and column.name == "set_config" for column in columns
            ):
                query_kinds.append("setup")
            elif len(columns) == sampler.EXPECTED_COLUMNS:
                query_kinds.append("projection")

    task: asyncio.Task[sampler.DeliveryQueueSnapshot] | None = None
    event.listen(engine.sync_engine, "before_cursor_execute", observe, named=True)
    try:
        async with sessions.begin() as session:
            baseline = await settings(session)
        monkeypatch.setattr(
            sampler, "open_transaction", inspected_transaction(original, finish, entered)
        )
        reader = sampler.SqlDeliveryQueueReader(sessions)
        if finish == "rollback":
            with pytest.raises(RuntimeError, match="synthetic post-read rollback"):
                await reader.snapshot()
        elif finish == "cancel":
            task = asyncio.create_task(reader.snapshot())
            await asyncio.wait_for(entered.wait(), timeout=2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            observed = await reader.snapshot()
            assert observed.sources_pending == 0
        assert query_kinds == ["setup", "projection"]
        assert isinstance(engine.pool, AsyncAdaptedQueuePool)
        assert engine.pool.checkedout() == 0
        async with sessions.begin() as session:
            assert await settings(session) == baseline
            await session.execute(
                text("UPDATE external_delivery_schedule SET turn=turn WHERE false")
            )
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        event.remove(engine.sync_engine, "before_cursor_execute", observe)
        await engine.dispose()
