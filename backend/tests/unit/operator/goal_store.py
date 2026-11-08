from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.goal_ports import (
    OperatorGoalFilters,
    OperatorGoalHistoryHead,
    OperatorGoalHistoryWindow,
    OperatorGoalRootPosition,
)
from studymate.domain.operator.goals import (
    OPERATOR_GOAL_PAGE_SIZE,
    OperatorGoalRevision,
    OperatorGoalRoot,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store

ACTIVE_GOAL = UUID(int=801)
COMPLETED_GOAL = UUID(int=802)
RAW_LABEL = " Original saved subject "
RAW_TOPIC = " Private historical topic "
RAW_KEY = " Legacy MATCH ß "
RAW_CONTEXT = " Private retained context\\n original "


def root(
    goal_id: UUID = ACTIVE_GOAL, account_id: UUID = TARGET, *, completed: bool = False
) -> OperatorGoalRoot:
    return OperatorGoalRoot(
        goal_id, account_id, 3, NOW - timedelta(days=1), NOW if completed else None
    )


def revision(
    version: int, goal_id: UUID = ACTIVE_GOAL, account_id: UUID = TARGET
) -> OperatorGoalRevision:
    return OperatorGoalRevision(
        goal_id,
        account_id,
        version,
        None,
        RAW_LABEL,
        RAW_TOPIC,
        RAW_KEY,
        RAW_CONTEXT,
        True,
        NOW - timedelta(minutes=version),
        None,
    )


class GoalStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.accounts = {TARGET}
        self.roots = {ACTIVE_GOAL: root(), COMPLETED_GOAL: root(COMPLETED_GOAL, completed=True)}
        self.revisions = {
            goal_id: tuple(revision(version, goal_id) for version in range(1, 4))
            for goal_id in self.roots
        }
        self.account_override: UUID | None = None
        self.head_override: OperatorGoalHistoryHead | None = None
        self.root_rows: tuple[OperatorGoalRoot, ...] | None = None
        self.revision_rows: tuple[OperatorGoalRevision, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["GoalStore"]:
        async with Store.transaction(self):
            yield self

    async def goal_account(self, account_id: UUID) -> UUID | None:
        self.queried()
        return (
            self.account_override
            if self.account_override is not None
            else account_id
            if account_id in self.accounts
            else None
        )

    async def goal_roots(
        self,
        account_id: UUID,
        filters: OperatorGoalFilters,
        position: OperatorGoalRootPosition | None,
    ) -> tuple[OperatorGoalRoot, ...]:
        self.queried()
        if self.root_rows is not None:
            return self.root_rows
        rows = (
            row
            for row in self.roots.values()
            if row.account_id == account_id
            and filters.matches(row)
            and (
                position is None
                or (
                    (row.created_at, row.id.int)
                    <= (position.anchor_created_at, position.anchor_goal_id.int)
                    and (row.created_at, row.id.int)
                    < (position.before_created_at, position.before_goal_id.int)
                )
            )
        )
        return tuple(sorted(rows, key=lambda row: (row.created_at, row.id.int), reverse=True))[
            : OPERATOR_GOAL_PAGE_SIZE + 1
        ]

    async def goal_history_head(
        self, account_id: UUID, goal_id: UUID
    ) -> OperatorGoalHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        value = self.roots.get(goal_id)
        if value is None or value.account_id != account_id:
            return None
        return OperatorGoalHistoryHead(value, max(row.version for row in self.revisions[goal_id]))

    async def goal_history_revisions(
        self, account_id: UUID, goal_id: UUID, window: OperatorGoalHistoryWindow
    ) -> tuple[OperatorGoalRevision, ...]:
        self.queried()
        if self.revision_rows is not None:
            return self.revision_rows
        rows = (
            row
            for row in self.revisions[goal_id]
            if row.account_id == account_id
            and row.version <= window.anchor_version
            and (window.before_version is None or row.version < window.before_version)
        )
        return tuple(sorted(rows, key=lambda row: row.version, reverse=True))[
            : OPERATOR_GOAL_PAGE_SIZE + 1
        ]
