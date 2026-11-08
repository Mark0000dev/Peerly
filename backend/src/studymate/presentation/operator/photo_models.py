"""Private raw profile-upload metadata; recorded states never imply object availability."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.operator.photo_ports import OperatorPhotoFilters
from studymate.application.operator.photo_uploads import (
    OperatorPhotoHistoryPage,
    OperatorPhotoUploadsPage,
)
from studymate.domain.media import PhotoFailure, PhotoUploadState
from studymate.domain.operator.photo_uploads import (
    MAX_OPERATOR_PHOTO_ATTEMPTS,
    OPERATOR_PHOTO_PAGE_SIZE,
    OperatorMediaOriginPhase,
    OperatorPhotoAttempt,
    OperatorPhotoAttemptOutcome,
    OperatorPhotoUploadRevision,
    OperatorPhotoUploadRoot,
    OperatorPublishedPhotoRef,
)
from studymate.presentation.operator.models import ClosedModel
from studymate.presentation.operator.timeline_models import (
    OperatorEventOriginResponse,
    origin_response,
)


class OperatorPhotoUploadsQuery(ClosedModel):
    state: PhotoUploadState | None = None
    created_from: AwareDatetime | None = None
    created_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorPhotoFilters:
        return OperatorPhotoFilters(self.state, self.created_from, self.created_before)

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class OperatorPhotoHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorPhotoRevisionResponse(ClosedModel):
    upload_id: UUID
    account_id: UUID
    version: int = Field(ge=1)
    state: PhotoUploadState
    updated_at: AwareDatetime
    attempt_id: UUID | None
    failure: PhotoFailure | None


class OperatorPhotoRootResponse(ClosedModel):
    id: UUID
    account_id: UUID
    current_version: int = Field(ge=1)
    expected_photo_version: int = Field(ge=0)
    source_size: int
    source_content_type: str
    source_sha256: str = Field(repr=False)
    source_metadata: Literal["declared_not_object_verified"] = "declared_not_object_verified"
    created_at: AwareDatetime
    upload_expires_at: AwareDatetime
    processing_expires_at: AwareDatetime
    current_revision: OperatorPhotoRevisionResponse


class OperatorPhotoUploadsResponse(ClosedModel):
    account_id: UUID
    uploads: tuple[OperatorPhotoRootResponse, ...] = Field(
        max_length=OPERATOR_PHOTO_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    anchor_created_at: AwareDatetime | None
    anchor_upload_id: UUID | None
    observed_at: AwareDatetime
    pagination: Literal["anchored_search_not_commit_order"] = "anchored_search_not_commit_order"


class OperatorPhotoAttemptResponse(ClosedModel):
    id: UUID
    upload_id: UUID
    number: int = Field(ge=1, le=MAX_OPERATOR_PHOTO_ATTEMPTS)
    started_at: AwareDatetime
    lease_until: AwareDatetime
    finished_at: AwareDatetime | None
    next_attempt_at: AwareDatetime | None
    outcome: OperatorPhotoAttemptOutcome
    failure: PhotoFailure | None
    display_width: int | None
    display_height: int | None
    display_size: int | None
    display_sha256: str | None = Field(repr=False)


class OperatorMediaOriginResponse(ClosedModel):
    upload_id: UUID
    phase: OperatorMediaOriginPhase
    origin: OperatorEventOriginResponse
    recorded_at: AwareDatetime


class OperatorPublishedPhotoRefResponse(ClosedModel):
    account_id: UUID
    photo_version: int = Field(ge=1)
    upload_id: UUID
    upload_version: int = Field(ge=1)
    saved_at: AwareDatetime


class OperatorPhotoHistoryResponse(ClosedModel):
    upload: OperatorPhotoRootResponse
    revisions: tuple[OperatorPhotoRevisionResponse, ...] = Field(
        max_length=OPERATOR_PHOTO_PAGE_SIZE
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=1)
    observed_at: AwareDatetime
    attempts_current: tuple[OperatorPhotoAttemptResponse, ...] = Field(
        max_length=MAX_OPERATOR_PHOTO_ATTEMPTS, repr=False
    )
    attempt_observation: Literal["current_recorded_not_revision_time"] = (
        "current_recorded_not_revision_time"
    )
    origins: tuple[OperatorMediaOriginResponse, ...] = Field(max_length=2)
    latest_published_photo_ref: OperatorPublishedPhotoRefResponse | None
    publication_scope: Literal["latest_recorded_ref_not_complete_history_or_object_grant"] = (
        "latest_recorded_ref_not_complete_history_or_object_grant"
    )


def revision_response(value: OperatorPhotoUploadRevision) -> OperatorPhotoRevisionResponse:
    return OperatorPhotoRevisionResponse(
        upload_id=value.upload_id,
        account_id=value.account_id,
        version=value.version,
        state=value.state,
        updated_at=value.updated_at,
        attempt_id=value.attempt_id,
        failure=value.failure,
    )


def root_response(value: OperatorPhotoUploadRoot) -> OperatorPhotoRootResponse:
    return OperatorPhotoRootResponse(
        id=value.id,
        account_id=value.account_id,
        current_version=value.current_version,
        expected_photo_version=value.expected_photo_version,
        source_size=value.source_size,
        source_content_type=value.source_content_type,
        source_sha256=value.source_sha256.hex(),
        created_at=value.created_at,
        upload_expires_at=value.upload_expires_at,
        processing_expires_at=value.processing_expires_at,
        current_revision=revision_response(value.current_revision),
    )


def attempt_response(value: OperatorPhotoAttempt) -> OperatorPhotoAttemptResponse:
    return OperatorPhotoAttemptResponse(
        id=value.id,
        upload_id=value.upload_id,
        number=value.number,
        started_at=value.started_at,
        lease_until=value.lease_until,
        finished_at=value.finished_at,
        next_attempt_at=value.next_attempt_at,
        outcome=value.outcome,
        failure=value.failure,
        display_width=value.display_width,
        display_height=value.display_height,
        display_size=value.display_size,
        display_sha256=value.display_sha256.hex() if value.display_sha256 is not None else None,
    )


def publication_response(value: OperatorPublishedPhotoRef) -> OperatorPublishedPhotoRefResponse:
    return OperatorPublishedPhotoRefResponse(
        account_id=value.account_id,
        photo_version=value.photo_version,
        upload_id=value.upload_id,
        upload_version=value.upload_version,
        saved_at=value.saved_at,
    )


def photo_uploads_response(value: OperatorPhotoUploadsPage) -> OperatorPhotoUploadsResponse:
    return OperatorPhotoUploadsResponse(
        account_id=value.account_id,
        uploads=tuple(root_response(row) for row in value.uploads),
        next_cursor=value.next_cursor,
        anchor_created_at=value.anchor_created_at,
        anchor_upload_id=value.anchor_upload_id,
        observed_at=value.observed_at,
    )


def photo_history_response(value: OperatorPhotoHistoryPage) -> OperatorPhotoHistoryResponse:
    publication = value.latest_published_photo_ref
    return OperatorPhotoHistoryResponse(
        upload=root_response(value.upload),
        revisions=tuple(revision_response(row) for row in value.revisions),
        next_cursor=value.next_cursor,
        anchor_version=value.anchor_version,
        observed_at=value.observed_at,
        attempts_current=tuple(attempt_response(row) for row in value.attempts_current),
        origins=tuple(
            OperatorMediaOriginResponse(
                upload_id=row.upload_id,
                phase=row.phase,
                origin=origin_response(row.origin),
                recorded_at=row.recorded_at,
            )
            for row in value.origins
        ),
        latest_published_photo_ref=publication_response(publication)
        if publication is not None
        else None,
    )
