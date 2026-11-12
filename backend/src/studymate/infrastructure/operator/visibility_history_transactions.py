"""Actual retained visibility rows; no event or exposure backfill."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.visibility_history_ports import (
    OperatorVisibilityHistoryHead,
    OperatorVisibilityHistoryWindow,
)
from studymate.domain.operator.visibility_history import (
    OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE,
    OperatorVisibilityHistoryRevision,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.onboarding_models import VisibilityRevisionRecord
from studymate.infrastructure.persistence.transactions import open_transaction


def visibility_history_value(row: VisibilityRevisionRecord) -> OperatorVisibilityHistoryRevision:
    return OperatorVisibilityHistoryRevision(
        row.account_id, row.version, row.completed_at, row.hidden_at, row.changed_at
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorVisibilityHistoryTransaction(SqlOperatorTransaction):
    async def visibility_history_head(
        self, account_id: UUID
    ) -> OperatorVisibilityHistoryHead | None:
        self.checked_access()
        exists = await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )
        if exists is None:
            return None
        row = await self.session.scalar(
            select(VisibilityRevisionRecord)
            .where(VisibilityRevisionRecord.account_id == account_id)
            .order_by(VisibilityRevisionRecord.version.desc())
            .limit(1)
        )
        current = visibility_history_value(row) if row is not None else None
        return OperatorVisibilityHistoryHead(
            account_id, current.version if current is not None else 0, current
        )

    async def visibility_history_revisions(
        self, account_id: UUID, window: OperatorVisibilityHistoryWindow
    ) -> tuple[OperatorVisibilityHistoryRevision, ...]:
        self.checked_access()
        statement = select(VisibilityRevisionRecord).where(
            VisibilityRevisionRecord.account_id == account_id,
            VisibilityRevisionRecord.version <= window.anchor_version,
        )
        if window.before_version is not None:
            statement = statement.where(VisibilityRevisionRecord.version < window.before_version)
        rows = await self.session.scalars(
            statement.order_by(VisibilityRevisionRecord.version.desc()).limit(
                OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE + 1
            )
        )
        return tuple(visibility_history_value(row) for row in rows)


@dataclass(frozen=True, slots=True)
class SqlOperatorVisibilityHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorVisibilityHistoryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorVisibilityHistoryTransaction(session, self.recorder)
