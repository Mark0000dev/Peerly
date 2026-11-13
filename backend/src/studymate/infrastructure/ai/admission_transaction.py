"""Acquire scarce AI SQL capacity before allocating an ORM transaction."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.persistence.transactions import open_transaction


@asynccontextmanager
async def admission_transaction(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    bind = sessions.kw.get("bind")
    if not isinstance(bind, AsyncEngine) or sessions.kw.get("binds"):
        # Connection-bound callers already own their checkout. Per-mapper
        # bindings may route elsewhere; do not reserve an unused connection.
        # Preserve their joining/routing semantics and the unbound test seam.
        async with open_transaction(sessions) as session:
            yield session
        return
    try:
        async with bind.connect() as connection:
            connected = async_sessionmaker(
                class_=sessions.class_, **(sessions.kw | {"bind": connection})
            )
            async with open_transaction(connected) as session:
                yield session
    except (OperationalError, InterfaceError, PoolTimeoutError, OSError):
        raise StorageUnavailableError from None
    except DBAPIError as error:
        if error.connection_invalidated or getattr(error.orig, "sqlstate", None) == "55P03":
            raise StorageUnavailableError from None
        raise
