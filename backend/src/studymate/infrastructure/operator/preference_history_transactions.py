"""Retained preference rows only; implicit student defaults are never inspection history."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.preference_history_ports import (
    OperatorPreferenceHistoryHead,
    OperatorPreferenceHistoryWindow,
)
from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.operator.preference_history import (
    OPERATOR_PREFERENCE_HISTORY_PAGE_SIZE,
    OperatorPreferenceHistoryRevision,
)
from studymate.infrastructure.notification_preferences.models import PreferenceRevisionRecord
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction


def preference_history_value(row: PreferenceRevisionRecord) -> OperatorPreferenceHistoryRevision:
    return OperatorPreferenceHistoryRevision(
        row.account_id, row.version, NotificationMode(row.mode), row.changed_at
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorPreferenceHistoryTransaction(SqlOperatorTransaction):
    async def preference_history_head(
        self, account_id: UUID
    ) -> OperatorPreferenceHistoryHead | None:
        self.checked_access()
        exists = await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )
        if exists is None:
            return None
        row = await self.session.scalar(
            select(PreferenceRevisionRecord)
            .where(PreferenceRevisionRecord.account_id == account_id)
            .order_by(PreferenceRevisionRecord.version.desc())
            .limit(1)
        )
        current = preference_history_value(row) if row is not None else None
        return OperatorPreferenceHistoryHead(
            account_id, current.version if current is not None else 0, current
        )

    async def preference_history_revisions(
        self, account_id: UUID, window: OperatorPreferenceHistoryWindow
    ) -> tuple[OperatorPreferenceHistoryRevision, ...]:
        self.checked_access()
        statement = select(PreferenceRevisionRecord).where(
            PreferenceRevisionRecord.account_id == account_id,
            PreferenceRevisionRecord.version <= window.anchor_version,
        )
        if window.before_version is not None:
            statement = statement.where(PreferenceRevisionRecord.version < window.before_version)
        rows = await self.session.scalars(
            statement.order_by(PreferenceRevisionRecord.version.desc()).limit(
                OPERATOR_PREFERENCE_HISTORY_PAGE_SIZE + 1
            )
        )
        return tuple(preference_history_value(row) for row in rows)


@dataclass(frozen=True, slots=True)
class SqlOperatorPreferenceHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorPreferenceHistoryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorPreferenceHistoryTransaction(session, self.recorder)
