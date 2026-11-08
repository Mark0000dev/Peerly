"""Actual retained chat-image preparation facts; READY is not a sent attachment."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.chat_images import ChatImageFailure, ChatImageState
from studymate.domain.messaging import MessageOutcome
from studymate.domain.time import require_aware

OPERATOR_CHAT_IMAGE_PAGE_SIZE = 50
MAX_OPERATOR_CHAT_IMAGE_VERSION = (1 << 31) - 1
MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS = 3


class OperatorChatImageAttemptOutcome(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    RETRY = "retry"
    REJECTED = "rejected"
    STALE = "stale"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class OperatorChatImageUploadRevision:
    image_id: UUID
    account_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    version: int
    state: ChatImageState
    updated_at: datetime
    attempt_id: UUID | None
    ready_attempt_outcome: OperatorChatImageAttemptOutcome | None
    failure: ChatImageFailure | None

    def __post_init__(self) -> None:
        require_aware(self.updated_at)
        if (
            isinstance(self.version, bool)
            or not 1 <= self.version <= MAX_OPERATOR_CHAT_IMAGE_VERSION
        ):
            raise ValueError("Chat image revision requires an actual bounded source version")


@dataclass(frozen=True, slots=True)
class OperatorChatImageUploadRoot:
    id: UUID
    account_id: UUID
    conversation_id: UUID
    low_id: UUID
    high_id: UUID
    client_message_id: UUID
    current_version: int
    source_size: int
    source_sha256: bytes = field(repr=False)
    source_content_type: str
    created_at: datetime
    upload_expires_at: datetime
    processing_expires_at: datetime
    current_revision: OperatorChatImageUploadRevision

    def __post_init__(self) -> None:
        for value in (self.created_at, self.upload_expires_at, self.processing_expires_at):
            require_aware(value)
        if (
            (
                self.current_revision.image_id,
                self.current_revision.account_id,
                self.current_revision.conversation_id,
                self.current_revision.client_message_id,
                self.current_revision.version,
            )
            != (
                self.id,
                self.account_id,
                self.conversation_id,
                self.client_message_id,
                self.current_version,
            )
            or self.low_id.int >= self.high_id.int
            or self.account_id not in (self.low_id, self.high_id)
        ):
            raise ValueError("Chat image metadata differs from its actual owned current revision")
        # Declared source metadata, not storage verification or binary authorization.


@dataclass(frozen=True, slots=True)
class OperatorChatImageAttempt:
    id: UUID
    image_id: UUID
    number: int
    started_at: datetime
    lease_until: datetime
    finished_at: datetime | None
    next_attempt_at: datetime | None
    outcome: OperatorChatImageAttemptOutcome
    failure: ChatImageFailure | None
    display_width: int | None
    display_height: int | None
    display_size: int | None
    display_sha256: bytes | None = field(repr=False)

    def __post_init__(self) -> None:
        for value in (self.started_at, self.lease_until, self.finished_at, self.next_attempt_at):
            if value is not None:
                require_aware(value)
        if (
            isinstance(self.number, bool)
            or not 1 <= self.number <= MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS
        ):
            raise ValueError("Chat image attempt requires its actual bounded attempt number")


@dataclass(frozen=True, slots=True)
class OperatorChatImageMatchingOperation:
    id: UUID
    author_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    state: MessageOutcome
    message_id: UUID | None
    cancelled_at: datetime | None

    def __post_init__(self) -> None:
        if self.cancelled_at is not None:
            require_aware(self.cancelled_at)
        # Matching client ID is NOT an image FK or proof of a sent attachment.
