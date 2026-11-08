from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.profile_history_ports import (
    OperatorProfileHistoryHead,
    OperatorProfileHistoryWindow,
)
from studymate.domain.operator.profile_history import (
    OPERATOR_PROFILE_HISTORY_PAGE_SIZE,
    OperatorProfileHistoryRevision,
)
from studymate.domain.profiles import OnboardingTask
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store


def revision(version: int, account_id: UUID = TARGET) -> OperatorProfileHistoryRevision:
    return OperatorProfileHistoryRevision(
        account_id,
        version,
        "  Original Name  ",
        " Private\n raw stored about ",
        " Original programme ",
        " Year 1 ",
        ("ms", "en"),
        OnboardingTask.FIND_HELP,
        NOW - timedelta(days=version),
    )


class HistoryStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.histories = {TARGET: tuple(revision(version) for version in range(1, 4))}
        self.head_override: OperatorProfileHistoryHead | None = None
        self.rows_override: tuple[OperatorProfileHistoryRevision, ...] | None = None
        self.last_history_window: OperatorProfileHistoryWindow | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["HistoryStore"]:
        async with Store.transaction(self):
            yield self

    async def profile_history_head(self, account_id: UUID) -> OperatorProfileHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        records = self.histories.get(account_id)
        return (
            OperatorProfileHistoryHead(account_id, max((row.version for row in records), default=0))
            if records is not None
            else None
        )

    async def profile_history_revisions(
        self, account_id: UUID, window: OperatorProfileHistoryWindow
    ) -> tuple[OperatorProfileHistoryRevision, ...]:
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
            : OPERATOR_PROFILE_HISTORY_PAGE_SIZE + 1
        ]
