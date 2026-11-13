import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import String, cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.application.ai.ports import AiUnavailableError
from studymate.bootstrap import create_ai_admission_engine
from studymate.infrastructure.ai import admission_transaction
from studymate.infrastructure.ai.models import AiSlotRecord
from studymate.infrastructure.ai.persistence import SqlAiUnitOfWork
from studymate.infrastructure.persistence.transactions import open_transaction

pytestmark = pytest.mark.integration


async def test_pool_rejection_and_cancelled_waiter_allocate_no_orm_transaction(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = 0

    @asynccontextmanager
    async def tracked(
        sessions: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[AsyncSession]:
        nonlocal entered
        entered += 1
        async with open_transaction(sessions) as session:
            yield session

    monkeypatch.setattr(admission_transaction, "open_transaction", tracked)
    engine = create_ai_admission_engine(database_url)
    uow = SqlAiUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))

    async def request() -> None:
        async with uow.transaction() as transaction:
            assert await transaction.session.scalar(select(1)) == 1

    try:
        async with engine.connect(), engine.connect():
            with pytest.raises(AiUnavailableError):
                await request()
            assert entered == 0
            waiter = asyncio.create_task(request())
            await asyncio.sleep(0)
            assert not waiter.done()
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert entered == 0
        await request()
        assert entered == 1
        assert isinstance(engine.pool, AsyncAdaptedQueuePool)
        assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose()


async def test_cancellation_of_active_write_rolls_back_before_capacity_returns(
    ai_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(ai_engine, expire_on_commit=False)
    uow = SqlAiUnitOfWork(sessions)
    written = asyncio.Event()
    async with sessions() as session:
        before = await session.scalar(select(AiSlotRecord.sequence))
    assert before is not None

    async def active_write() -> None:
        async with uow.transaction() as transaction:
            await transaction.session.execute(update(AiSlotRecord).values(sequence=before + 1))
            written.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(active_write())
    try:
        async with asyncio.timeout(2):
            await written.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with uow.transaction() as transaction:
            assert await transaction.session.scalar(select(AiSlotRecord.sequence)) == before
        assert isinstance(ai_engine.pool, AsyncAdaptedQueuePool)
        assert ai_engine.pool.checkedout() == 0
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


async def test_connection_bound_savepoint_does_not_commit_callers_transaction(
    ai_engine: AsyncEngine,
) -> None:
    async with ai_engine.connect() as connection, connection.begin() as outer:
        before = await connection.scalar(select(AiSlotRecord.sequence))
        assert before is not None
        sessions = async_sessionmaker(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with SqlAiUnitOfWork(sessions).transaction() as transaction:
            await transaction.session.execute(update(AiSlotRecord).values(sequence=before + 1))
        assert outer.is_active
        assert await connection.scalar(select(AiSlotRecord.sequence)) == before + 1
        await outer.rollback()
    async with async_sessionmaker(ai_engine)() as session:
        assert await session.scalar(select(AiSlotRecord.sequence)) == before


async def test_checked_out_session_owns_commit_rollback_and_releases_connection(
    ai_engine: AsyncEngine, database_url: str
) -> None:
    async with ai_engine.connect() as connection:
        schema = await connection.scalar(select(cast(func.current_schema(), String)))
    assert schema is not None
    engine = create_ai_admission_engine(database_url, server_settings={"search_path": schema})

    class AdmissionSession(AsyncSession):
        pass

    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine,
        class_=AdmissionSession,
        expire_on_commit=False,
        autoflush=False,
        info={"control": "kept"},
    )
    uow = SqlAiUnitOfWork(sessions)
    try:
        async with uow.transaction() as transaction:
            before = await transaction.session.scalar(select(AiSlotRecord.sequence))
            assert before is not None
            assert transaction.session.info["control"] == "kept"
            assert isinstance(transaction.session, AdmissionSession)
            assert not transaction.session.sync_session.autoflush
            assert not transaction.session.sync_session.expire_on_commit

        async def rollback_control() -> None:
            async with uow.transaction() as transaction:
                await transaction.session.execute(update(AiSlotRecord).values(sequence=before + 1))
                raise ValueError("rollback control")

        with pytest.raises(ValueError, match="rollback control"):
            await rollback_control()
        async with uow.transaction() as transaction:
            assert await transaction.session.scalar(select(AiSlotRecord.sequence)) == before
            await transaction.session.execute(update(AiSlotRecord).values(sequence=before + 2))
        async with uow.transaction() as transaction:
            assert await transaction.session.scalar(select(AiSlotRecord.sequence)) == before + 2
        assert isinstance(engine.pool, AsyncAdaptedQueuePool)
        assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose()
