from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from studymate.application.messaging.ports import MessageTransaction
from studymate.domain.messaging import ConfirmedMessage

MESSAGE_HISTORY_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class MessageHistoryWindow:
    anchor_sequence: int
    before_sequence: int | None


@dataclass(frozen=True, slots=True)
class MessageHistoryPage:
    messages: tuple[ConfirmedMessage, ...] = field(repr=False)
    next_cursor: str | None
    anchor_sequence: int


class MessageHistoryTransaction(MessageTransaction, Protocol):
    async def history_messages(
        self, actor_id: UUID, conversation_id: UUID, window: MessageHistoryWindow
    ) -> tuple[ConfirmedMessage, ...]:
        """Owned SQL filter before payload, descending sequence50+lookahead, no N+1."""
        ...


class MessageHistoryUnitOfWork(Protocol):
    def transaction(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[MessageHistoryTransaction]: ...
