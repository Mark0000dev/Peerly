from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError


@asynccontextmanager
async def open_transaction(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    try:
        async with sessions.begin() as session:
            yield session
    except (OperationalError, InterfaceError, PoolTimeoutError, OSError):
        raise StorageUnavailableError from None
    except DBAPIError as error:
        if error.connection_invalidated:
            raise StorageUnavailableError from None
        # Constraint/programming errors are not disguised as availability failures.
        raise
