"""Account-owned raw goal sources; no GoalContent/StudyGoal/current catalogue reconstruction."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.goal_ports import (
    OperatorGoalFilters,
    OperatorGoalHistoryHead,
    OperatorGoalHistoryWindow,
    OperatorGoalRootPosition,
    OperatorGoalState,
)
from studymate.domain.operator.goals import (
    OPERATOR_GOAL_PAGE_SIZE,
    OperatorGoalRevision,
    OperatorGoalRoot,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.goal_models import GoalRecord, GoalRevisionRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction


def root_value(record: GoalRecord) -> OperatorGoalRoot:
    return OperatorGoalRoot(
        record.id, record.account_id, record.current_version, record.created_at, record.completed_at
    )


def revision_value(record: GoalRevisionRecord) -> OperatorGoalRevision:
    return OperatorGoalRevision(
        record.goal_id,
        record.account_id,
        record.version,
        record.subject_id,
        record.subject_label,
        record.topic,
        record.topic_match_key,
        record.context,
        record.shared_learning,
        record.saved_at,
        record.completed_at,
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorGoalTransaction(SqlOperatorTransaction):
    async def goal_account(self, account_id: UUID) -> UUID | None:
        self.checked_access()
        return await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )

    async def goal_roots(
        self,
        account_id: UUID,
        filters: OperatorGoalFilters,
        position: OperatorGoalRootPosition | None,
    ) -> tuple[OperatorGoalRoot, ...]:
        self.checked_access()
        statement = select(GoalRecord).where(GoalRecord.account_id == account_id)
        if filters.state == OperatorGoalState.ACTIVE:
            statement = statement.where(GoalRecord.completed_at.is_(None))
        elif filters.state == OperatorGoalState.COMPLETED:
            statement = statement.where(GoalRecord.completed_at.is_not(None))
        if filters.created_from is not None:
            statement = statement.where(GoalRecord.created_at >= filters.created_from)
        if filters.created_before is not None:
            statement = statement.where(GoalRecord.created_at < filters.created_before)
        if position is not None:
            statement = statement.where(
                tuple_(GoalRecord.created_at, GoalRecord.id)
                <= tuple_(position.anchor_created_at, position.anchor_goal_id),
                tuple_(GoalRecord.created_at, GoalRecord.id)
                < tuple_(position.before_created_at, position.before_goal_id),
            )
        rows = tuple(
            await self.session.scalars(
                statement.order_by(GoalRecord.created_at.desc(), GoalRecord.id.desc()).limit(
                    OPERATOR_GOAL_PAGE_SIZE + 1
                )
            )
        )
        return tuple(root_value(record) for record in rows)

    async def goal_history_head(
        self, account_id: UUID, goal_id: UUID
    ) -> OperatorGoalHistoryHead | None:
        self.checked_access()
        root = await self.session.scalar(
            select(GoalRecord).where(GoalRecord.id == goal_id, GoalRecord.account_id == account_id)
        )
        if root is None:
            return None
        latest = await self.session.scalar(
            select(func.max(GoalRevisionRecord.version)).where(
                GoalRevisionRecord.goal_id == goal_id, GoalRevisionRecord.account_id == account_id
            )
        )
        if latest is None:
            raise RuntimeError("Retained goal root lost its committed revision source")
        return OperatorGoalHistoryHead(root_value(root), latest)

    async def goal_history_revisions(
        self, account_id: UUID, goal_id: UUID, window: OperatorGoalHistoryWindow
    ) -> tuple[OperatorGoalRevision, ...]:
        self.checked_access()
        statement = select(GoalRevisionRecord).where(
            GoalRevisionRecord.goal_id == goal_id,
            GoalRevisionRecord.account_id == account_id,
            GoalRevisionRecord.version <= window.anchor_version,
        )
        if window.before_version is not None:
            statement = statement.where(GoalRevisionRecord.version < window.before_version)
        rows = tuple(
            await self.session.scalars(
                statement.order_by(GoalRevisionRecord.version.desc()).limit(
                    OPERATOR_GOAL_PAGE_SIZE + 1
                )
            )
        )
        return tuple(revision_value(record) for record in rows)


@dataclass(frozen=True, slots=True)
class SqlOperatorGoalUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorGoalTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorGoalTransaction(session, self.recorder)
