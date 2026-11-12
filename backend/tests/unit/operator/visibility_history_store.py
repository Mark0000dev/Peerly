from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.visibility_history_ports import (
    OperatorVisibilityHistoryHead,
    OperatorVisibilityHistoryWindow,
)
from studymate.domain.operator.visibility_history import (
    OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE,
    OperatorVisibilityHistoryRevision,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store


def revision(version: int, account_id: UUID = TARGET) -> OperatorVisibilityHistoryRevision:
    changed = NOW - timedelta(days=version)
    return OperatorVisibilityHistoryRevision(
        account_id,
        version,
        NOW - timedelta(days=365),
        changed if version % 2 == 0 else None,
        changed,
    )


class HistoryStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.histories = {TARGET: tuple(revision(version) for version in range(1, 4))}
        self.head_override: OperatorVisibilityHistoryHead | None = None
        self.rows_override: tuple[OperatorVisibilityHistoryRevision, ...] | None = None
        self.last_history_window: OperatorVisibilityHistoryWindow | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["HistoryStore"]:
        async with Store.transaction(self):
            yield self

    async def visibility_history_head(
        self, account_id: UUID
    ) -> OperatorVisibilityHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        records = self.histories.get(account_id)
        if records is None:
            return None
        current = max(records, key=lambda row: row.version) if records else None
        return OperatorVisibilityHistoryHead(account_id, current.version if current else 0, current)

    async def visibility_history_revisions(
        self, account_id: UUID, window: OperatorVisibilityHistoryWindow
    ) -> tuple[OperatorVisibilityHistoryRevision, ...]:
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
            : OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE + 1
        ]
