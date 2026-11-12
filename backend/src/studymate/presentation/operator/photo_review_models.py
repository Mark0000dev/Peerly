"""Closed human-review DTOs; ordinary owner recovery excludes private rationale."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from studymate.application.operator.photo_review_ports import PhotoReviewTarget
from studymate.domain.media import PhotoRevision
from studymate.domain.operator.photo_review import (
    MAX_PHOTO_REVIEW_REASON,
    PhotoRecoveryState,
    PhotoReviewAction,
    PhotoReviewRecovery,
    PhotoReviewRevision,
)
from studymate.domain.text import plain_text
from studymate.presentation.operator.models import ClosedModel


class PhotoReviewBody(ClosedModel):
    expected_version: int = Field(ge=0, strict=True)
    expected_photo_version: int = Field(ge=1, strict=True)
    expected_upload_id: UUID
    action: PhotoReviewAction
    reason: str = Field(min_length=1, max_length=MAX_PHOTO_REVIEW_REASON, repr=False)

    @model_validator(mode="after")
    def valid_human_reason(self) -> Self:
        plain_text(self.reason, minimum=1, maximum=MAX_PHOTO_REVIEW_REASON, multiline=True)
        return self


class PhotoReviewPhotoResponse(ClosedModel):
    version: int
    upload_id: UUID
    saved_at: datetime


class PhotoReviewResponse(ClosedModel):
    id: UUID
    account_id: UUID
    version: int
    previous_revision_id: UUID | None
    action: PhotoReviewAction
    photo: PhotoReviewPhotoResponse
    operator_id: UUID
    session_id: UUID
    grant_version: int
    decided_at: datetime
    reason: str = Field(repr=False)
    http_request_id: UUID | None
    action_id: UUID | None
    trace_id: str | None
    span_id: str | None


class PhotoReviewContextResponse(ClosedModel):
    account_id: UUID
    current_photo: PhotoReviewPhotoResponse | None
    current_review: PhotoReviewResponse | None


class OwnPhotoReviewResponse(ClosedModel):
    version: int
    state: PhotoRecoveryState


def photo_review_photo(photo: PhotoRevision) -> PhotoReviewPhotoResponse:
    return PhotoReviewPhotoResponse(
        version=photo.version, upload_id=photo.upload_id, saved_at=photo.saved_at
    )


def photo_review_response(source: PhotoReviewRevision) -> PhotoReviewResponse:
    return PhotoReviewResponse(
        id=source.id,
        account_id=source.account_id,
        version=source.version,
        previous_revision_id=source.previous_revision_id,
        action=source.action,
        photo=photo_review_photo(source.photo),
        operator_id=source.operator_id,
        session_id=source.session_id,
        grant_version=source.grant_version,
        decided_at=source.decided_at,
        reason=source.reason,
        http_request_id=source.origin.http_request_id,
        action_id=source.origin.action_id,
        trace_id=source.origin.trace_id,
        span_id=source.origin.span_id,
    )


def photo_review_context(source: PhotoReviewTarget) -> PhotoReviewContextResponse:
    return PhotoReviewContextResponse(
        account_id=source.account_id,
        current_photo=photo_review_photo(source.current_photo)
        if source.current_photo is not None
        else None,
        current_review=photo_review_response(source.current_review)
        if source.current_review is not None
        else None,
    )


def own_photo_review_response(source: PhotoReviewRecovery) -> OwnPhotoReviewResponse:
    return OwnPhotoReviewResponse(version=source.version, state=source.state)
