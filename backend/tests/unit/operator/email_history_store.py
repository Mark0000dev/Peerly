from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.email_history_ports import EmailHistoryWindow
from studymate.domain.operator.email_history import EMAIL_HISTORY_PAGE_SIZE, EmailHistoryChallenge
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store


def challenge(index: int, account_id: UUID = TARGET) -> EmailHistoryChallenge:
    return EmailHistoryChallenge(
        UUID(int=index),
        account_id,
        UUID(int=900),
        "retained-private@mail.apu.edu.my",
        NOW - timedelta(minutes=index),
        NOW + timedelta(minutes=20),
        NOW + timedelta(minutes=1),
        2,
        None,
        None,
        None,
        None,
    )


class EmailHistoryStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.histories: dict[UUID, tuple[EmailHistoryChallenge, ...]] = {
            TARGET: (challenge(1), challenge(2))
        }
        self.rows_override: tuple[EmailHistoryChallenge, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["EmailHistoryStore"]:
        async with Store.transaction(self):
            yield self

    async def email_history_account_exists(self, account_id: UUID) -> bool:
        self.queried()
        return account_id in self.histories

    async def email_history_challenges(
        self, account_id: UUID, window: EmailHistoryWindow
    ) -> tuple[EmailHistoryChallenge, ...]:
        self.queried()
        if self.rows_override is not None:
            return self.rows_override
        rows = (
            row
            for row in self.histories[account_id]
            if row.created_at <= window.as_of
            and (
                window.before is None
                or (row.created_at, row.id) < (window.before.created_at, window.before.challenge_id)
            )
        )
        return tuple(sorted(rows, key=lambda row: (row.created_at, row.id), reverse=True))[
            : EMAIL_HISTORY_PAGE_SIZE + 1
        ]
