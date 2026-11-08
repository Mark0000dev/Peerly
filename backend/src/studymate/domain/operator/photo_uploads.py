"""Recorded profile-photo metadata only; no storage object verification or access grant."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.media import PhotoFailure, PhotoUploadState
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.time import require_aware

OPERATOR_PHOTO_PAGE_SIZE = 50
MAX_OPERATOR_PHOTO_VERSION = (1 << 31) - 1
MAX_OPERATOR_PHOTO_ATTEMPTS = 3
MAX_OPERATOR_MEDIA_ORIGINS = 2


class OperatorPhotoAttemptOutcome(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    RETRY = "retry"
    REJECTED = "rejected"
    STALE = "stale"
    INTERRUPTED = "interrupted"


class OperatorMediaOriginPhase(StrEnum):
    CREATED = "created"
    QUEUED = "queued"


@dataclass(frozen=True, slots=True)
class OperatorPhotoUploadRevision:
    upload_id: UUID
    account_id: UUID
    version: int
    state: PhotoUploadState
    updated_at: datetime
    attempt_id: UUID | None
    failure: PhotoFailure | None

    def __post_init__(self) -> None:
        require_aware(self.updated_at)
        if isinstance(self.version, bool) or not 1 <= self.version <= MAX_OPERATOR_PHOTO_VERSION:
            raise ValueError("Recorded photo revision requires an actual bounded source version")


@dataclass(frozen=True, slots=True)
class OperatorPhotoUploadRoot:
    id: UUID
    account_id: UUID
    current_version: int
    expected_photo_version: int
    source_size: int
    source_sha256: bytes = field(repr=False)
    source_content_type: str
    created_at: datetime
    upload_expires_at: datetime
    processing_expires_at: datetime
    current_revision: OperatorPhotoUploadRevision

    def __post_init__(self) -> None:
        for value in (self.created_at, self.upload_expires_at, self.processing_expires_at):
            require_aware(value)
        if (
            self.current_revision.upload_id != self.id
            or self.current_revision.account_id != self.account_id
            or self.current_revision.version != self.current_version
        ):
            raise ValueError("Photo upload metadata differs from its actual owned current revision")
        # Source size/type/fingerprint are declared upload metadata, NOT object verification.


@dataclass(frozen=True, slots=True)
class OperatorPhotoAttempt:
    id: UUID
    upload_id: UUID
    number: int
    started_at: datetime
    lease_until: datetime
    finished_at: datetime | None
    next_attempt_at: datetime | None
    outcome: OperatorPhotoAttemptOutcome
    failure: PhotoFailure | None
    display_width: int | None
    display_height: int | None
    display_size: int | None
    display_sha256: bytes | None = field(repr=False)

    def __post_init__(self) -> None:
        for value in (self.started_at, self.lease_until, self.finished_at, self.next_attempt_at):
            if value is not None:
                require_aware(value)
        if isinstance(self.number, bool) or not 1 <= self.number <= MAX_OPERATOR_PHOTO_ATTEMPTS:
            raise ValueError("Photo attempt metadata requires its actual bounded attempt number")
        # CURRENT recorded mutable outcome, never reconstructed as revision-time state.


@dataclass(frozen=True, slots=True)
class OperatorMediaOrigin:
    upload_id: UUID
    phase: OperatorMediaOriginPhase
    origin: OperatorEventOrigin
    recorded_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.recorded_at)


@dataclass(frozen=True, slots=True)
class OperatorPublishedPhotoRef:
    account_id: UUID
    photo_version: int
    upload_id: UUID
    upload_version: int
    saved_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.saved_at)
        # A recorded publication reference does not prove object presence/current access.
