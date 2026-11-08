from uuid import UUID, uuid4

import pytest
from sqlalchemy import String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from studymate.infrastructure.persistence.database import SqlDatabaseProbe

pytestmark = pytest.mark.integration


class PersistenceBase(DeclarativeBase):
    pass


class PersistenceRecord(PersistenceBase):
    __tablename__ = "integration_records"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(100), unique=True)


async def test_asyncpg_probe_uses_real_postgresql(engine: AsyncEngine) -> None:
    assert await SqlDatabaseProbe(async_sessionmaker(engine)).is_available()


async def test_committed_data_survives_new_session_and_rollback_is_isolated(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(PersistenceBase.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    identity = uuid4()
    async with sessions.begin() as session:
        session.add(PersistenceRecord(id=identity, label="committed"))
    async with sessions() as session:
        record = await session.get(PersistenceRecord, identity)
        assert record is not None
        assert record.label == "committed"
        session.add(PersistenceRecord(id=uuid4(), label="rolled-back"))
        await session.flush()
        await session.rollback()
    async with sessions() as session:
        assert (await session.scalars(select(PersistenceRecord.label))).all() == ["committed"]


async def test_database_enforces_unique_constraints(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(PersistenceBase.metadata.create_all)
    sessions = async_sessionmaker(engine)
    async with sessions.begin() as session:
        session.add(PersistenceRecord(id=uuid4(), label="same"))
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            session.add(PersistenceRecord(id=uuid4(), label="same"))
