"""Actual accepted-pair and intentional human-message evidence, without bodies."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from studymate.domain.messaging import ChatConversation, ConfirmedMessage
from studymate.domain.relationships import AccountPair
from studymate.domain.time import require_aware

PROMPT_DELAY = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class HumanMessageEvidence:
    id: UUID
    conversation_id: UUID
    author_id: UUID
    sequence: int
    sent_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.sent_at)
        if isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("Human message evidence requires an actual confirmed sequence")

    @classmethod
    def from_message(cls, message: ConfirmedMessage) -> "HumanMessageEvidence":
        return cls(
            message.id,
            message.conversation_id,
            message.author_id,
            message.sequence,
            message.sent_at,
        )


@dataclass(frozen=True, slots=True)
class AcceptedConversationRef:
    """Immutable accepted context only, excluding the mutable next-message counter."""

    id: UUID
    relationship_id: UUID
    pair: AccountPair
    request_id: UUID
    accepted_request_version: int

    def __post_init__(self) -> None:
        if isinstance(self.accepted_request_version, bool) or self.accepted_request_version <= 1:
            raise ValueError("Feedback source requires an actual accepted request revision")

    @classmethod
    def from_conversation(cls, conversation: ChatConversation) -> "AcceptedConversationRef":
        return cls(
            conversation.id,
            conversation.relationship_id,
            conversation.pair,
            conversation.request_id,
            conversation.accepted_request_version,
        )


@dataclass(frozen=True, slots=True)
class InteractionEvidence:
    conversation: AcceptedConversationRef
    accepted_at: datetime
    low_message: HumanMessageEvidence | None = None
    high_message: HumanMessageEvidence | None = None

    def __post_init__(self) -> None:
        require_aware(self.accepted_at)
        for message, author in (
            (self.low_message, self.conversation.pair.low),
            (self.high_message, self.conversation.pair.high),
        ):
            if message is not None and (
                message.conversation_id != self.conversation.id or message.author_id != author
            ):
                raise ValueError("Human evidence differs from its accepted conversation source")
        if (
            self.low_message is not None
            and self.high_message is not None
            and (
                self.low_message.id == self.high_message.id
                or self.low_message.sequence == self.high_message.sequence
            )
        ):
            raise ValueError("Two-way evidence requires two distinct confirmed messages")

    @classmethod
    def from_conversation(
        cls,
        conversation: ChatConversation,
        accepted_at: datetime,
        low_message: HumanMessageEvidence | None = None,
        high_message: HumanMessageEvidence | None = None,
    ) -> "InteractionEvidence":
        if any(
            message is not None and message.sequence >= conversation.next_message_sequence
            for message in (low_message, high_message)
        ):
            raise ValueError("Human evidence exceeds the actual committed conversation sequence")
        return cls(
            AcceptedConversationRef.from_conversation(conversation),
            accepted_at,
            low_message,
            high_message,
        )

    @property
    def two_way(self) -> bool:
        return self.low_message is not None and self.high_message is not None

    def prompt_available(self, at: datetime) -> bool:
        require_aware(at)
        return self.two_way and at >= self.accepted_at + PROMPT_DELAY
