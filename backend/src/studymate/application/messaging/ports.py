from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentityReader
from studymate.domain.messaging import ChatConversation, MessageContent, MessageOperation


class ConversationUnavailableError(Exception):
    pass


class MessageContactUnavailableError(Exception):
    pass


class MessageImageUnavailableError(Exception):
    pass


class ClientMessageConflictError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ConversationAccess:
    conversation: ChatConversation
    peer_verified: bool
    peer_banned: bool
    peer_deleted: bool
    blocked: bool

    @property
    def can_send(self) -> bool:
        return self.peer_verified and not (self.peer_banned or self.peer_deleted or self.blocked)


@dataclass(frozen=True, slots=True)
class MessageIntent:
    fingerprint: bytes = field(repr=False)
    operation: MessageOperation = field(repr=False)


class ConversationAuthority(IdentityReader, Protocol):
    """Actual live identity plus accepted membership; no message-write capabilities."""

    async def conversation(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConversationAccess | None: ...


class MessageTransaction(ConversationAuthority, Protocol):
    """Conversation-derived sorted account locks precede session and conversation.

    Opaque ID lookups supply lock scope only. All methods and outcome writes use
    this same SQL transaction; no storage/network calls belong inside it.
    """

    async def message_intent(
        self, actor_id: UUID, operation: str, key: IntentKey
    ) -> MessageIntent | None: ...

    async def message_operation(
        self, actor_id: UUID, conversation_id: UUID, client_message_id: UUID
    ) -> MessageOperation | None: ...

    async def admit_message_content(
        self,
        actor_id: UUID,
        conversation_id: UUID,
        client_message_id: UUID,
        content: MessageContent,
    ) -> None:
        """Resolve the exact owned Ready source; text cannot reuse a source-bound intent."""
        ...

    async def save_message_operation(self, operation: MessageOperation) -> None:
        """Atomically persist terminal root/message, actual sequence and canonical outcome."""
        ...

    async def cancel_image_preparation(self, operation: MessageOperation) -> None:
        """Close pending preparation/attempt after a new cancellation, in the same transaction."""
        ...

    async def remember_message_intent(
        self, actor_id: UUID, operation: str, key: IntentKey, intent: MessageIntent, at: datetime
    ) -> None: ...


class MessageUnitOfWork(Protocol):
    def transaction(
        self, conversation_id: UUID
    ) -> AbstractAsyncContextManager[MessageTransaction]: ...
