from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.help_history_ports import (
    OperatorHelpHistoryHead,
    OperatorHelpHistoryWindow,
)
from studymate.domain.operator.help_history import (
    OPERATOR_HELP_HISTORY_PAGE_SIZE,
    OperatorHelpHistoryRevision,
    OperatorHelpHistorySelection,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store

SUBJECT = UUID(int=701)
SECOND_SUBJECT = UUID(int=702)
RAW_LABEL = " Original saved subject "
RAW_NOTE = " Private retained topic "
RAW_KEY = "Legacy MATCH ß unchanged"
CLEAR_VERSION = 2


def revision(version: int, account_id: UUID = TARGET) -> OperatorHelpHistoryRevision:
    selections = (
        ()
        if version == CLEAR_VERSION
        else (
            OperatorHelpHistorySelection(1, SUBJECT, RAW_LABEL, RAW_NOTE, RAW_KEY),
            OperatorHelpHistorySelection(4, SECOND_SUBJECT, " Second original label ", None, None),
        )
    )
    return OperatorHelpHistoryRevision(
        account_id, version, selections, NOW - timedelta(days=version)
    )


class HelpHistoryStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.histories = {TARGET: tuple(revision(version) for version in range(1, 4))}
        self.head_override: OperatorHelpHistoryHead | None = None
        self.rows_override: tuple[OperatorHelpHistoryRevision, ...] | None = None
        self.last_history_window: OperatorHelpHistoryWindow | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["HelpHistoryStore"]:
        async with Store.transaction(self):
            yield self

    async def help_history_head(self, account_id: UUID) -> OperatorHelpHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        records = self.histories.get(account_id)
        return (
            OperatorHelpHistoryHead(account_id, max((row.version for row in records), default=0))
            if records is not None
            else None
        )

    async def help_history_revisions(
        self, account_id: UUID, window: OperatorHelpHistoryWindow
    ) -> tuple[OperatorHelpHistoryRevision, ...]:
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
            : OPERATOR_HELP_HISTORY_PAGE_SIZE + 1
        ]
