"""Raw retained help revisions/selections; no current pointer/catalogue/domain reconstruction."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.help_history_ports import (
    OperatorHelpHistoryHead,
    OperatorHelpHistoryWindow,
)
from studymate.domain.operator.help_history import (
    OPERATOR_HELP_HISTORY_PAGE_SIZE,
    OperatorHelpHistoryRevision,
    OperatorHelpHistorySelection,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.help_models import HelpRevisionRecord, HelpSelectionRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorHelpHistoryTransaction(SqlOperatorTransaction):
    async def help_history_head(self, account_id: UUID) -> OperatorHelpHistoryHead | None:
        self.checked_access()
        exists = await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )
        if exists is None:
            return None
        latest = await self.session.scalar(
            select(func.max(HelpRevisionRecord.version)).where(
                HelpRevisionRecord.account_id == account_id
            )
        )
        return OperatorHelpHistoryHead(account_id, latest if latest is not None else 0)

    async def help_history_revisions(
        self, account_id: UUID, window: OperatorHelpHistoryWindow
    ) -> tuple[OperatorHelpHistoryRevision, ...]:
        self.checked_access()
        statement = select(HelpRevisionRecord).where(
            HelpRevisionRecord.account_id == account_id,
            HelpRevisionRecord.version <= window.anchor_version,
        )
        if window.before_version is not None:
            statement = statement.where(HelpRevisionRecord.version < window.before_version)
        revisions = tuple(
            await self.session.scalars(
                statement.order_by(HelpRevisionRecord.version.desc()).limit(
                    OPERATOR_HELP_HISTORY_PAGE_SIZE + 1
                )
            )
        )
        if not revisions:
            return ()
        selections: dict[int, list[OperatorHelpHistorySelection]] = {
            row.version: [] for row in revisions
        }
        records = tuple(
            await self.session.scalars(
                select(HelpSelectionRecord)
                .where(
                    HelpSelectionRecord.account_id == account_id,
                    HelpSelectionRecord.version.in_(selections),
                )
                .order_by(HelpSelectionRecord.version, HelpSelectionRecord.slot)
            )
        )
        for record in records:
            selections[record.version].append(
                OperatorHelpHistorySelection(
                    record.slot,
                    record.subject_id,
                    record.subject_label,
                    record.topic_note,
                    record.topic_match_key,
                )
            )
        return tuple(
            OperatorHelpHistoryRevision(
                row.account_id, row.version, tuple(selections[row.version]), row.saved_at
            )
            for row in revisions
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorHelpHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorHelpHistoryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorHelpHistoryTransaction(session, self.recorder)
