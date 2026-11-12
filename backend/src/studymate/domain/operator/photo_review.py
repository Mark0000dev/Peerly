"""Human photo decisions; independent of storage processing and account lifecycle."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.media import PhotoRevision
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.text import plain_text
from studymate.domain.time import require_aware

MAX_PHOTO_REVIEW_REASON = 1000


class PhotoReviewAction(StrEnum):
    REQUIRE_REPLACEMENT = "require_replacement"
    APPROVE_REPLACEMENT = "approve_replacement"


class PhotoRecoveryState(StrEnum):
    NOT_REQUIRED = "not_required"
    REPLACEMENT_REQUIRED = "replacement_required"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"


@dataclass(frozen=True, slots=True)
class PhotoReviewRecovery:
    version: int
    state: PhotoRecoveryState


@dataclass(frozen=True, slots=True)
class PhotoReviewRevision:
    id: UUID
    account_id: UUID
    version: int
    previous_revision_id: UUID | None
    action: PhotoReviewAction
    photo: PhotoRevision
    operator_id: UUID
    session_id: UUID
    grant_version: int
    decided_at: datetime
    reason: str = field(repr=False)
    origin: OperatorEventOrigin = field(default_factory=OperatorEventOrigin)

    def __post_init__(self) -> None:
        require_aware(self.decided_at)
        if (
            isinstance(self.version, bool)
            or self.version < 1
            or isinstance(self.grant_version, bool)
            or self.grant_version < 1
        ):
            raise ValueError("Photo review requires positive source revisions")
        if (self.version == 1) != (self.previous_revision_id is None):
            raise ValueError("Photo review must retain its exact previous revision")
        if self.photo.account_id != self.account_id or self.photo.saved_at > self.decided_at:
            raise ValueError("Photo review must refer to an already published owned photo")
        if self.version == 1 and self.action != PhotoReviewAction.REQUIRE_REPLACEMENT:
            raise ValueError("Approval requires an actual prior replacement requirement")
        object.__setattr__(
            self,
            "reason",
            plain_text(self.reason, minimum=1, maximum=MAX_PHOTO_REVIEW_REASON, multiline=True),
        )

    @property
    def replacement_required(self) -> bool:
        return self.action == PhotoReviewAction.REQUIRE_REPLACEMENT

    def validate_successor(self, successor: "PhotoReviewRevision") -> None:
        """Validate immutable continuity; use cases separately recheck live authority."""
        if (
            successor.account_id != self.account_id
            or successor.version != self.version + 1
            or successor.previous_revision_id != self.id
            or successor.decided_at < self.decided_at
        ):
            raise ValueError("Photo review successor does not extend its exact source")
        if successor.action == PhotoReviewAction.APPROVE_REPLACEMENT and (
            not self.replacement_required
            or successor.photo.version <= self.photo.version
            or successor.photo.upload_id == self.photo.upload_id
        ):
            raise ValueError("Human approval requires a new replacement photo")


def photo_review_recovery(
    review: PhotoReviewRevision | None, current_photo: PhotoRevision | None
) -> PhotoReviewRecovery:
    if review is None:
        return PhotoReviewRecovery(0, PhotoRecoveryState.NOT_REQUIRED)
    if current_photo is not None and current_photo.account_id != review.account_id:
        raise ValueError("Photo recovery sources must belong to one account")
    if not review.replacement_required:
        return PhotoReviewRecovery(review.version, PhotoRecoveryState.NOT_REQUIRED)
    replaced = (
        current_photo is not None
        and current_photo.version > review.photo.version
        and current_photo.upload_id != review.photo.upload_id
    )
    return PhotoReviewRecovery(
        review.version,
        PhotoRecoveryState.AWAITING_HUMAN_REVIEW
        if replaced
        else PhotoRecoveryState.REPLACEMENT_REQUIRED,
    )
