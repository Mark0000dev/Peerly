from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.time import require_aware

MAX_PHOTO_BYTES = 10_000_000
SHA256_LENGTH = 32


class MediaObjectKind(StrEnum):
    UPLOAD = "upload"
    ORIGINAL = "original"
    DISPLAY = "display"


@dataclass(frozen=True, slots=True)
class MediaObjectRef:
    upload_id: UUID
    kind: MediaObjectKind
    attempt_id: UUID | None = None

    def __post_init__(self) -> None:
        if (self.kind == MediaObjectKind.UPLOAD) != (self.attempt_id is None):
            raise ValueError("Retained objects require a processing attempt identity")


class PhotoUploadState(StrEnum):
    UPLOADING = "uploading"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PhotoFailure(StrEnum):
    INVALID_IMAGE = "invalid_image"
    UNSUPPORTED_FORMAT = "unsupported_format"
    TOO_LARGE = "too_large"
    DIMENSIONS_EXCEEDED = "dimensions_exceeded"
    ANIMATED_IMAGE = "animated_image"
    CONTENT_CHANGED = "content_changed"
    PHOTO_CHANGED = "photo_changed"
    ACCOUNT_UNAVAILABLE = "account_unavailable"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    PROCESSING_UNAVAILABLE = "processing_unavailable"


class PhotoContentType(StrEnum):
    JPEG = "image/jpeg"
    PNG = "image/png"


@dataclass(frozen=True, slots=True)
class PhotoSource:
    size: int
    sha256: bytes = field(repr=False)
    content_type: PhotoContentType

    def __post_init__(self) -> None:
        if isinstance(self.size, bool) or not 1 <= self.size <= MAX_PHOTO_BYTES:
            raise ValueError("Photo source size is outside the allowed range")
        if len(self.sha256) != SHA256_LENGTH:
            raise ValueError("Photo source digest must be SHA256")


@dataclass(frozen=True, slots=True)
class PhotoUpload:
    id: UUID
    account_id: UUID
    source: PhotoSource = field(repr=False)
    expected_photo_version: int
    created_at: datetime
    upload_expires_at: datetime
    processing_expires_at: datetime
    updated_at: datetime
    version: int = 1
    state: PhotoUploadState = PhotoUploadState.UPLOADING
    attempt_id: UUID | None = None
    failure: PhotoFailure | None = None

    def __post_init__(self) -> None:
        for value in (self.created_at, self.upload_expires_at, self.processing_expires_at):
            require_aware(value)
        require_aware(self.updated_at)
        if self.updated_at < self.created_at:
            raise ValueError("Upload revision cannot precede creation")
        if not self.created_at < self.upload_expires_at <= self.processing_expires_at:
            raise ValueError("Upload deadlines must follow creation")
        if (
            isinstance(self.version, bool)
            or self.version < 1
            or isinstance(self.expected_photo_version, bool)
            or self.expected_photo_version < 0
        ):
            raise ValueError("Photo revisions must be valid integers")
        if (self.state == PhotoUploadState.REJECTED) != (self.failure is not None):
            raise ValueError("Rejected upload must explain its failure")
        if (
            self.state in {PhotoUploadState.PROCESSING, PhotoUploadState.READY}
            and self.attempt_id is None
        ):
            raise ValueError("Processing and ready uploads require an attempt")

    @property
    def pending(self) -> bool:
        return self.state in {
            PhotoUploadState.UPLOADING,
            PhotoUploadState.QUEUED,
            PhotoUploadState.PROCESSING,
        }

    def _at(self, at: datetime) -> None:
        require_aware(at)
        if at < self.updated_at:
            raise ValueError("Upload action cannot precede the current revision")

    def queue(self, at: datetime) -> "PhotoUpload":
        self._at(at)
        expired = self.expire(at)
        if expired is not self:
            return expired
        if self.state != PhotoUploadState.UPLOADING:
            return self
        return replace(self, version=self.version + 1, state=PhotoUploadState.QUEUED, updated_at=at)

    def cancel(self, at: datetime) -> "PhotoUpload":
        self._at(at)
        if not self.pending:
            return self
        state = (
            PhotoUploadState.EXPIRED
            if (
                at >= self.processing_expires_at
                or (self.state == PhotoUploadState.UPLOADING and at >= self.upload_expires_at)
            )
            else PhotoUploadState.CANCELLED
        )
        return replace(self, version=self.version + 1, state=state, updated_at=at)

    def expire(self, at: datetime) -> "PhotoUpload":
        self._at(at)
        deadline = (
            self.upload_expires_at
            if self.state == PhotoUploadState.UPLOADING
            else self.processing_expires_at
        )
        if not self.pending or at < deadline:
            return self
        return replace(
            self, version=self.version + 1, state=PhotoUploadState.EXPIRED, updated_at=at
        )

    def processing(self, attempt_id: UUID, at: datetime) -> "PhotoUpload":
        self._at(at)
        if self.state not in {PhotoUploadState.QUEUED, PhotoUploadState.PROCESSING}:
            raise ValueError("Only queued or reclaimed uploads can begin processing")
        expired = self.expire(at)
        if expired is not self:
            return expired
        return replace(
            self,
            version=self.version + 1,
            state=PhotoUploadState.PROCESSING,
            updated_at=at,
            attempt_id=attempt_id,
        )

    def retry(self, at: datetime) -> "PhotoUpload":
        self._at(at)
        if self.state != PhotoUploadState.PROCESSING:
            raise ValueError("Only a processing upload can be retried")
        expired = self.expire(at)
        if expired is not self:
            return expired
        return replace(self, version=self.version + 1, state=PhotoUploadState.QUEUED, updated_at=at)

    def ready(self, attempt_id: UUID, at: datetime) -> "PhotoUpload":
        self._at(at)
        if self.state != PhotoUploadState.PROCESSING or self.attempt_id != attempt_id:
            raise ValueError("Only the current processing attempt can finalize")
        expired = self.expire(at)
        if expired is not self:
            return expired
        return replace(self, version=self.version + 1, state=PhotoUploadState.READY, updated_at=at)

    def reject(self, failure: PhotoFailure, at: datetime) -> "PhotoUpload":
        self._at(at)
        if not self.pending:
            return self
        expired = self.expire(at)
        if expired is not self:
            return expired
        return replace(
            self,
            version=self.version + 1,
            state=PhotoUploadState.REJECTED,
            updated_at=at,
            failure=failure,
        )


@dataclass(frozen=True, slots=True)
class PhotoRevision:
    account_id: UUID
    version: int
    upload_id: UUID
    saved_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.saved_at)
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Published photo version must be positive")
