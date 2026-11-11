from collections.abc import AsyncIterator, Sized
from contextlib import asynccontextmanager
from typing import Protocol

from sqlalchemy import event
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import ORMExecuteState

from studymate.application.errors import StorageUnavailableError

IDENTITY_READ_ONLY_KEY = "studymate.read_only_identity"


class PendingChanges(Protocol):
    @property
    def new(self) -> Sized: ...

    @property
    def dirty(self) -> Sized: ...

    @property
    def deleted(self) -> Sized: ...


def _read_statement(state: ORMExecuteState) -> None:
    if not state.is_select:
        raise RuntimeError("Read-only identity unit cannot execute mutations")


def _read_flush(session: PendingChanges, _context: object, _instances: object) -> None:
    if session.new or session.dirty or session.deleted:
        raise RuntimeError("Read-only identity unit cannot flush mutations")


@asynccontextmanager
async def open_transaction(
    sessions: async_sessionmaker[AsyncSession],
    *,
    read_only: bool = False,
) -> AsyncIterator[AsyncSession]:
    try:
        async with sessions.begin() as session:
            if read_only:
                session.info[IDENTITY_READ_ONLY_KEY] = True
                event.listen(session.sync_session, "do_orm_execute", _read_statement)
                event.listen(session.sync_session, "before_flush", _read_flush)
            try:
                yield session
                if read_only:
                    # Commit happens outside this context's finally: reject pending
                    # ORM changes before removing our instance-scoped listeners.
                    _read_flush(session.sync_session, None, None)
            finally:
                if read_only:
                    event.remove(session.sync_session, "do_orm_execute", _read_statement)
                    event.remove(session.sync_session, "before_flush", _read_flush)
                    session.info.pop(IDENTITY_READ_ONLY_KEY, None)
    except (OperationalError, InterfaceError, PoolTimeoutError, OSError):
        raise StorageUnavailableError from None
    except DBAPIError as error:
        if error.connection_invalidated or getattr(error.orig, "sqlstate", None) == "55P03":
            raise StorageUnavailableError from None
        # Lock unavailability is retryable; constraint/programming errors remain visible.
        raise
