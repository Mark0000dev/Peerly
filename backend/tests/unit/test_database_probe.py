from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from studymate.infrastructure.persistence.database import SqlDatabaseProbe


@pytest.mark.parametrize("error", [SQLAlchemyError("unavailable"), OSError("refused")])
async def test_expected_database_failures_report_unavailable(error: Exception) -> None:
    engine = create_async_engine("postgresql+asyncpg://localhost/unused")
    try:
        with patch.object(AsyncSession, "execute", side_effect=error):
            assert not await SqlDatabaseProbe(async_sessionmaker(engine)).is_available()
    finally:
        await engine.dispose()


async def test_programming_errors_are_not_swallowed() -> None:
    engine = create_async_engine("postgresql+asyncpg://localhost/unused")
    try:
        with (
            patch.object(AsyncSession, "execute", side_effect=RuntimeError("bug")),
            pytest.raises(RuntimeError, match="bug"),
        ):
            await SqlDatabaseProbe(async_sessionmaker(engine)).is_available()
    finally:
        await engine.dispose()
