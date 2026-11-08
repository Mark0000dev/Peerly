"""Confirmed messages and terminal send intents; wall time never orders messages."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.relationships import AccountPair
from studymate.domain.text import plain_text
from studymate.domain.time import require_aware

MAX_MESSAGE_LENGTH = 2000


@dataclass(frozen=True, slots=True)
class MessageContent:
    text: str | None = field(default=None, repr=False)
    image_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.text is None and self.image_id is None:
            raise ValueError("Message needs text or one image")
        if self.text is not None:
            if len(self.text) > MAX_MESSAGE_LENGTH:
                raise ValueError("Message text exceeds 2000 code points")
            plain_text(self.text, minimum=1, maximum=MAX_MESSAGE_LENGTH, multiline=True)


@dataclass(frozen=True, slots=True)
class ChatConversation:
    id: UUID
    relationship_id: UUID
    pair: AccountPair
    request_id: UUID
    accepted_request_version: int
    next_message_sequence: int

    def __post_init__(self) -> None:
        if isinstance(self.accepted_request_version, bool) or self.accepted_request_version <= 1:
            raise ValueError("Conversation requires a real accepted request revision")
        if isinstance(self.next_message_sequence, bool) or self.next_message_sequence < 1:
            raise ValueError("Conversation message sequence must be positive")


@dataclass(frozen=True, slots=True)
class ConfirmedMessage:
    id: UUID
    operation_id: UUID
    conversation_id: UUID
    pair: AccountPair
    author_id: UUID
    client_message_id: UUID
    sequence: int
    content: MessageContent = field(repr=False)
    sent_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.sent_at)
        if self.author_id not in (self.pair.low, self.pair.high):
            raise ValueError("Message author must be a conversation participant")
        if isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("Confirmed message requires a positive sequence")


class MessageOutcome(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class MessageOperation:
    id: UUID
    conversation_id: UUID
    pair: AccountPair
    author_id: UUID
    client_message_id: UUID
    message: ConfirmedMessage | None = field(default=None, repr=False)
    cancelled_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.author_id not in (self.pair.low, self.pair.high):
            raise ValueError("Message operation belongs to a conversation participant")
        if (self.message is None) == (self.cancelled_at is None):
            raise ValueError("Message operation has exactly one terminal outcome")
        if self.cancelled_at is not None:
            require_aware(self.cancelled_at)
        if self.message is not None and (
            self.message.operation_id != self.id
            or self.message.conversation_id != self.conversation_id
            or self.message.pair != self.pair
            or self.message.author_id != self.author_id
            or self.message.client_message_id != self.client_message_id
        ):
            raise ValueError("Confirmed message disagrees with its immutable operation")

    @property
    def outcome(self) -> MessageOutcome:
        return MessageOutcome.CONFIRMED if self.message is not None else MessageOutcome.CANCELLED
