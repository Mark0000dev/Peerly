"""Conversation-bound image preparation; READY is not a sent message."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.media import PhotoSource
from studymate.domain.time import require_aware


class ChatImageState(StrEnum):
    UPLOADING = "uploading"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ChatImageFailure(StrEnum):
    INVALID_IMAGE = "invalid_image"
    UNSUPPORTED_FORMAT = "unsupported_format"
    TOO_LARGE = "too_large"
    DIMENSIONS_EXCEEDED = "dimensions_exceeded"
    ANIMATED_IMAGE = "animated_image"
    CONTENT_CHANGED = "content_changed"
    ACCOUNT_UNAVAILABLE = "account_unavailable"
    CONTACT_UNAVAILABLE = "contact_unavailable"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    PROCESSING_UNAVAILABLE = "processing_unavailable"


@dataclass(frozen=True, slots=True)
class ChatImagePreparation:
    id: UUID
    account_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    source: PhotoSource = field(repr=False)
    created_at: datetime
    upload_expires_at: datetime
    processing_expires_at: datetime
    updated_at: datetime
    version: int = 1
    state: ChatImageState = ChatImageState.UPLOADING
    attempt_id: UUID | None = None
    failure: ChatImageFailure | None = None

    def __post_init__(self) -> None:
        for value in (
            self.created_at,
            self.upload_expires_at,
            self.processing_expires_at,
            self.updated_at,
        ):
            require_aware(value)
        if not self.created_at < self.upload_expires_at <= self.processing_expires_at:
            raise ValueError("Image preparation deadlines must follow creation")
        if self.updated_at < self.created_at:
            raise ValueError("Image preparation revision cannot precede creation")
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Image preparation revision must be positive")
        if (self.state == ChatImageState.REJECTED) != (self.failure is not None):
            raise ValueError("Rejected image preparation requires its failure")
        if (
            self.state in {ChatImageState.PROCESSING, ChatImageState.READY}
            and self.attempt_id is None
        ):
            raise ValueError("Processing and ready images require an actual attempt")

    @property
    def pending(self) -> bool:
        return self.state in {
            ChatImageState.UPLOADING,
            ChatImageState.QUEUED,
            ChatImageState.PROCESSING,
        }

    def _at(self, at: datetime) -> None:
        require_aware(at)
        if at < self.updated_at:
            raise ValueError("Image preparation action cannot precede its current revision")

    def expire(self, at: datetime) -> "ChatImagePreparation":
        self._at(at)
        deadline = (
            self.upload_expires_at
            if self.state == ChatImageState.UPLOADING
            else self.processing_expires_at
        )
        if not self.pending or at < deadline:
            return self
        return replace(self, version=self.version + 1, state=ChatImageState.EXPIRED, updated_at=at)

    def queue(self, at: datetime) -> "ChatImagePreparation":
        self._at(at)
        current = self.expire(at)
        if current is not self or self.state != ChatImageState.UPLOADING:
            return current
        return replace(self, version=self.version + 1, state=ChatImageState.QUEUED, updated_at=at)

    def cancel(self, at: datetime) -> "ChatImagePreparation":
        self._at(at)
        if not self.pending:
            return self
        current = self.expire(at)
        if current is not self:
            return current
        return replace(
            self, version=self.version + 1, state=ChatImageState.CANCELLED, updated_at=at
        )

    def claim(self, attempt_id: UUID, at: datetime) -> "ChatImagePreparation":
        self._at(at)
        if self.state not in {ChatImageState.QUEUED, ChatImageState.PROCESSING}:
            raise ValueError("Only a queued or reclaimed image can begin processing")
        current = self.expire(at)
        if current is not self:
            return current
        return replace(
            self,
            version=self.version + 1,
            state=ChatImageState.PROCESSING,
            attempt_id=attempt_id,
            updated_at=at,
        )

    def retry(self, at: datetime) -> "ChatImagePreparation":
        self._at(at)
        if self.state != ChatImageState.PROCESSING:
            raise ValueError("Only a processing image can be retried")
        current = self.expire(at)
        if current is not self:
            return current
        return replace(self, version=self.version + 1, state=ChatImageState.QUEUED, updated_at=at)

    def ready(self, attempt_id: UUID, at: datetime) -> "ChatImagePreparation":
        self._at(at)
        if self.state != ChatImageState.PROCESSING or self.attempt_id != attempt_id:
            raise ValueError("Only the actual current image attempt can finish")
        current = self.expire(at)
        if current is not self:
            return current
        return replace(self, version=self.version + 1, state=ChatImageState.READY, updated_at=at)

    def reject(self, failure: ChatImageFailure, at: datetime) -> "ChatImagePreparation":
        self._at(at)
        if not self.pending:
            return self
        current = self.expire(at)
        if current is not self:
            return current
        return replace(
            self,
            version=self.version + 1,
            state=ChatImageState.REJECTED,
            failure=failure,
            updated_at=at,
        )
