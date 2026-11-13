"""Account-scoped bounded metadata projection; never load token digests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import load_only

from studymate.application.operator.session_history_ports import SessionHistoryWindow
from studymate.domain.operator.session_history import SESSION_HISTORY_PAGE_SIZE, SessionHistoryEntry
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorSessionHistoryTransaction(SqlOperatorTransaction):
    async def session_history_account_exists(self, account_id: UUID) -> bool:
        self.checked_access()
        return (
            await self.session.scalar(
                select(AccountRecord.id).where(AccountRecord.id == account_id)
            )
            is not None
        )

    async def session_history_sessions(
        self, account_id: UUID, window: SessionHistoryWindow
    ) -> tuple[SessionHistoryEntry, ...]:
        self.checked_access()
        model = SessionRecord
        statement = (
            select(model)
            .where(model.account_id == account_id, model.issued_at <= window.as_of)
            .options(
                load_only(
                    model.id,
                    model.account_id,
                    model.issued_at,
                    model.expires_at,
                    model.revoked_at,
                    raiseload=True,
                )
            )
        )
        if window.before is not None:
            statement = statement.where(
                tuple_(model.issued_at, model.id)
                < tuple_(window.before.issued_at, window.before.session_id)
            )
        rows = await self.session.scalars(
            statement.order_by(model.issued_at.desc(), model.id.desc()).limit(
                SESSION_HISTORY_PAGE_SIZE + 1
            )
        )
        return tuple(
            SessionHistoryEntry(
                row.id, row.account_id, row.issued_at, row.expires_at, row.revoked_at
            )
            for row in rows
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorSessionHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorSessionHistoryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorSessionHistoryTransaction(session, self.recorder)
