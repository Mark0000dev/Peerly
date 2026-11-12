from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.access_history_ports import (
    OperatorAccessHistoryHead,
    OperatorAccessHistoryWindow,
)
from studymate.domain.operator.access_history import (
    OPERATOR_ACCESS_HISTORY_PAGE_SIZE,
    OperatorAccessHistoryRevision,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store


def revision(version: int, account_id: UUID = TARGET) -> OperatorAccessHistoryRevision:
    return OperatorAccessHistoryRevision(
        account_id=account_id,
        version=version,
        active=version % 2 == 1,
        changed_at=NOW - timedelta(days=version),
        changed_by_id=UUID(int=100) if version > 1 else None,
        http_request_id=None,
        action_id=None,
        trace_id=None,
        span_id=None,
    )


class HistoryStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.histories = {TARGET: tuple(revision(version) for version in range(1, 4))}
        self.head_override: OperatorAccessHistoryHead | None = None
        self.rows_override: tuple[OperatorAccessHistoryRevision, ...] | None = None
        self.last_history_window: OperatorAccessHistoryWindow | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["HistoryStore"]:
        async with Store.transaction(self):
            yield self

    async def access_history_head(self, account_id: UUID) -> OperatorAccessHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        records = self.histories.get(account_id)
        return (
            OperatorAccessHistoryHead(account_id, max((row.version for row in records), default=0))
            if records is not None
            else None
        )

    async def access_history_revisions(
        self, account_id: UUID, window: OperatorAccessHistoryWindow
    ) -> tuple[OperatorAccessHistoryRevision, ...]:
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
            : OPERATOR_ACCESS_HISTORY_PAGE_SIZE + 1
        ]
