from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.conversation_index import OperatorConversationSummary


@dataclass(frozen=True, slots=True)
class OperatorConversationPosition:
    before_id: UUID


class OperatorConversationCursorCodec(Protocol):
    def encode_conversations(
        self, scope: OperatorCursorScope, account_id: UUID, position: OperatorConversationPosition
    ) -> str: ...

    def decode_conversations(
        self, scope: OperatorCursorScope, account_id: UUID, token: str
    ) -> OperatorConversationPosition: ...


class OperatorConversationIndexTransaction(OperatorAuditTransaction, Protocol):
    async def conversation_account(self, account_id: UUID) -> UUID | None: ...

    async def indexed_conversations(
        self, account_id: UUID, position: OperatorConversationPosition | None
    ) -> tuple[OperatorConversationSummary, ...]:
        """UUID id DESC,50+lookahead, actual low/high participation; never message content."""
        ...


class OperatorConversationIndexUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorConversationIndexTransaction]: ...
