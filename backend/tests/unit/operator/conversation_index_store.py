from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from studymate.application.operator.conversation_index_ports import OperatorConversationPosition
from studymate.domain.operator.conversation_index import (
    OPERATOR_CONVERSATION_PAGE_SIZE,
    OperatorConversationSummary,
)
from tests.unit.operator.store import TARGET, Store


class ConversationIndexStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.rows: tuple[OperatorConversationSummary, ...] = ()
        self.override_rows: tuple[OperatorConversationSummary, ...] | None = None
        self.accounts = {TARGET}

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["ConversationIndexStore"]:
        async with Store.transaction(self):
            yield self

    async def conversation_account(self, account_id: UUID) -> UUID | None:
        self.queried()
        return account_id if account_id in self.accounts else None

    async def indexed_conversations(
        self, account_id: UUID, position: OperatorConversationPosition | None
    ) -> tuple[OperatorConversationSummary, ...]:
        self.queried()
        if self.override_rows is not None:
            return self.override_rows
        rows = tuple(
            row
            for row in self.rows
            if row.includes(account_id)
            and (position is None or row.id.int < position.before_id.int)
        )
        return tuple(sorted(rows, key=lambda row: row.id.int, reverse=True))[
            : OPERATOR_CONVERSATION_PAGE_SIZE + 1
        ]
