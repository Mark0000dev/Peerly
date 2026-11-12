from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.preference_history_ports import (
    OperatorPreferenceHistoryHead,
    OperatorPreferenceHistoryWindow,
)
from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.operator.preference_history import (
    OPERATOR_PREFERENCE_HISTORY_PAGE_SIZE,
    OperatorPreferenceHistoryRevision,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store


def revision(version: int, account_id: UUID = TARGET) -> OperatorPreferenceHistoryRevision:
    return OperatorPreferenceHistoryRevision(
        account_id,
        version,
        NotificationMode.ALL_UPDATES if version % 2 else NotificationMode.MESSAGES_AND_REQUESTS,
        NOW - timedelta(days=version),
    )


class HistoryStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.histories = {TARGET: tuple(revision(version) for version in range(1, 4))}
        self.head_override: OperatorPreferenceHistoryHead | None = None
        self.rows_override: tuple[OperatorPreferenceHistoryRevision, ...] | None = None
        self.last_history_window: OperatorPreferenceHistoryWindow | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["HistoryStore"]:
        async with Store.transaction(self):
            yield self

    async def preference_history_head(
        self, account_id: UUID
    ) -> OperatorPreferenceHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        records = self.histories.get(account_id)
        if records is None:
            return None
        current = max(records, key=lambda row: row.version) if records else None
        return OperatorPreferenceHistoryHead(account_id, current.version if current else 0, current)

    async def preference_history_revisions(
        self, account_id: UUID, window: OperatorPreferenceHistoryWindow
    ) -> tuple[OperatorPreferenceHistoryRevision, ...]:
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
            : OPERATOR_PREFERENCE_HISTORY_PAGE_SIZE + 1
        ]
