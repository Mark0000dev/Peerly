"""Standalone CLI resources; no application Settings, dotenv, credentials or providers."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from studymate.application.bootstrap_data.ports import (
    BootstrapDatabaseConfigurationError,
    BootstrapDatabaseOperationError,
)

BOOTSTRAP_APPLY_SECONDS = 45


@asynccontextmanager
async def open_bootstrap_database(
    database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    try:
        parsed = make_url(database_url)
    except (ArgumentError, ValueError):
        raise BootstrapDatabaseConfigurationError from None
    if parsed.drivername != "postgresql+asyncpg" or not parsed.database:
        raise BootstrapDatabaseConfigurationError
    engine = create_async_engine(
        parsed,
        pool_size=1,
        max_overflow=0,
        pool_timeout=3,
        connect_args={
            "timeout": 3,
            "command_timeout": 30,
            "server_settings": {"statement_timeout": "30000", "lock_timeout": "5000"},
        },
    )
    try:
        async with asyncio.timeout(BOOTSTRAP_APPLY_SECONDS):
            yield async_sessionmaker(engine, expire_on_commit=False)
    except SQLAlchemyError:
        # Constraints/programming errors are not disguised as availability or success.
        # The command returns a distinct failure code without SQL/input/DSN details.
        raise BootstrapDatabaseOperationError from None
    finally:
        await engine.dispose()
