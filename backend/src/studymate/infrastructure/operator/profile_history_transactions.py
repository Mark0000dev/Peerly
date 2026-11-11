"""Actual retained profile/language reads; no current pointer/photo joins or student filter."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.profile_history_ports import (
    OperatorProfileHistoryHead,
    OperatorProfileHistoryWindow,
)
from studymate.domain.operator.profile_history import (
    OPERATOR_PROFILE_HISTORY_PAGE_SIZE,
    OperatorProfileHistoryRevision,
)
from studymate.domain.profiles import OnboardingTask
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.profile_models import (
    ProfileLanguageRecord,
    ProfileRevisionRecord,
)
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorProfileHistoryTransaction(SqlOperatorTransaction):
    async def profile_history_head(self, account_id: UUID) -> OperatorProfileHistoryHead | None:
        self.checked_access()
        exists = await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )
        if exists is None:
            return None
        latest = await self.session.scalar(
            select(func.max(ProfileRevisionRecord.version)).where(
                ProfileRevisionRecord.account_id == account_id
            )
        )
        return OperatorProfileHistoryHead(account_id, latest if latest is not None else 0)

    async def profile_history_revisions(
        self, account_id: UUID, window: OperatorProfileHistoryWindow
    ) -> tuple[OperatorProfileHistoryRevision, ...]:
        self.checked_access()
        statement = select(ProfileRevisionRecord).where(
            ProfileRevisionRecord.account_id == account_id,
            ProfileRevisionRecord.version <= window.anchor_version,
        )
        if window.before_version is not None:
            statement = statement.where(ProfileRevisionRecord.version < window.before_version)
        revisions = tuple(
            await self.session.scalars(
                statement.order_by(ProfileRevisionRecord.version.desc()).limit(
                    OPERATOR_PROFILE_HISTORY_PAGE_SIZE + 1
                )
            )
        )
        if not revisions:
            return ()
        languages: dict[int, list[str]] = {row.version: [] for row in revisions}
        rows = (
            await self.session.execute(
                select(ProfileLanguageRecord.version, ProfileLanguageRecord.code)
                .where(
                    ProfileLanguageRecord.account_id == account_id,
                    ProfileLanguageRecord.version.in_(languages),
                )
                .order_by(ProfileLanguageRecord.version, ProfileLanguageRecord.slot)
            )
        ).all()
        for version, code in rows:
            languages[version].append(code)
        return tuple(
            OperatorProfileHistoryRevision(
                row.account_id,
                row.version,
                row.display_name,
                row.about,
                row.programme,
                row.year_label,
                tuple(languages[row.version]),
                OnboardingTask(row.task),
                row.saved_at,
            )
            for row in revisions
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorProfileHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorProfileHistoryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorProfileHistoryTransaction(session, self.recorder)
