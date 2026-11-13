from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.session_history_ports import SessionHistoryWindow
from studymate.domain.operator.session_history import SESSION_HISTORY_PAGE_SIZE, SessionHistoryEntry
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store


def entry(index: int, account_id: UUID = TARGET) -> SessionHistoryEntry:
    return SessionHistoryEntry(
        UUID(int=index), account_id, NOW - timedelta(minutes=index), NOW + timedelta(days=7), None
    )


class SessionHistoryStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.histories: dict[UUID, tuple[SessionHistoryEntry, ...]] = {TARGET: (entry(1), entry(2))}
        self.rows_override: tuple[SessionHistoryEntry, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["SessionHistoryStore"]:
        async with Store.transaction(self):
            yield self

    async def session_history_account_exists(self, account_id: UUID) -> bool:
        self.queried()
        return account_id in self.histories

    async def session_history_sessions(
        self, account_id: UUID, window: SessionHistoryWindow
    ) -> tuple[SessionHistoryEntry, ...]:
        self.queried()
        if self.rows_override is not None:
            return self.rows_override
        rows = (
            row
            for row in self.histories[account_id]
            if row.issued_at <= window.as_of
            and (
                window.before is None
                or (row.issued_at, row.id) < (window.before.issued_at, window.before.session_id)
            )
        )
        return tuple(sorted(rows, key=lambda row: (row.issued_at, row.id), reverse=True))[
            : SESSION_HISTORY_PAGE_SIZE + 1
        ]
