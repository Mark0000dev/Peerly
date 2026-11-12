from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.lifecycle_history_ports import (
    OperatorLifecycleHistoryHead,
    OperatorLifecycleHistoryWindow,
)
from studymate.domain.lifecycle.states import LifecycleOperation
from studymate.domain.operator.lifecycle_history import (
    OPERATOR_LIFECYCLE_HISTORY_PAGE_SIZE,
    OperatorLifecycleHistoryRevision,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store


def revision(version: int, account_id: UUID = TARGET) -> OperatorLifecycleHistoryRevision:
    return OperatorLifecycleHistoryRevision(
        UUID(int=version),
        account_id,
        version,
        version - 1 if version > 1 else None,
        LifecycleOperation.BAN,
        None,
        None,
        NOW,
        None,
        NOW - timedelta(days=version),
        UUID(int=100),
        UUID(int=101),
        1,
        True,
        "  Private exact reason  ",
        None,
        None,
        None,
        None,
        None,
    )


class HistoryStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.histories = {TARGET: tuple(revision(version) for version in range(1, 4))}
        self.head_override: OperatorLifecycleHistoryHead | None = None
        self.rows_override: tuple[OperatorLifecycleHistoryRevision, ...] | None = None
        self.last_history_window: OperatorLifecycleHistoryWindow | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["HistoryStore"]:
        async with Store.transaction(self):
            yield self

    async def lifecycle_history_head(self, account_id: UUID) -> OperatorLifecycleHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        records = self.histories.get(account_id)
        return (
            OperatorLifecycleHistoryHead(
                account_id, max((row.version for row in records), default=0)
            )
            if records is not None
            else None
        )

    async def lifecycle_history_revisions(
        self, account_id: UUID, window: OperatorLifecycleHistoryWindow
    ) -> tuple[OperatorLifecycleHistoryRevision, ...]:
        self.queried()
        self.last_history_window = window
        if self.rows_override is not None:
            return self.rows_override
        rows = (
            row
            for row in self.histories[account_id]
            if row.version <= window.anchor_version
            and (window.before_version is None or row.version < window.before_version)
        )
        return tuple(sorted(rows, key=lambda row: row.version, reverse=True))[
            : OPERATOR_LIFECYCLE_HISTORY_PAGE_SIZE + 1
        ]
