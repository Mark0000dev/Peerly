"""Private raw chat-image preparation metadata; recorded states never imply object availability."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.operator.chat_image_ports import OperatorChatImageFilters
from studymate.application.operator.chat_image_uploads import (
    OperatorChatImageHistoryPage,
    OperatorChatImageUploadsPage,
)
from studymate.domain.chat_images import ChatImageFailure, ChatImageState
from studymate.domain.messaging import MessageOutcome
from studymate.domain.operator.chat_image_uploads import (
    MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS,
    OPERATOR_CHAT_IMAGE_PAGE_SIZE,
    OperatorChatImageAttempt,
    OperatorChatImageAttemptOutcome,
    OperatorChatImageMatchingOperation,
    OperatorChatImageUploadRevision,
    OperatorChatImageUploadRoot,
)
from studymate.presentation.operator.models import ClosedModel


class OperatorChatImageUploadsQuery(ClosedModel):
    conversation_id: UUID | None = None
    state: ChatImageState | None = None
    created_from: AwareDatetime | None = None
    created_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorChatImageFilters:
        return OperatorChatImageFilters(
            self.conversation_id, self.state, self.created_from, self.created_before
        )

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class OperatorChatImageHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorChatImageRevisionResponse(ClosedModel):
    image_id: UUID
    account_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    version: int = Field(ge=1)
    state: ChatImageState
    updated_at: AwareDatetime
    attempt_id: UUID | None
    ready_attempt_outcome: OperatorChatImageAttemptOutcome | None
    failure: ChatImageFailure | None


class OperatorChatImageRootResponse(ClosedModel):
    id: UUID
    account_id: UUID
    current_version: int = Field(ge=1)
    conversation_id: UUID
    low_id: UUID
    high_id: UUID
    client_message_id: UUID
    source_size: int
    source_content_type: str
    source_sha256: str = Field(repr=False)
    source_metadata: Literal["declared_not_object_verified"] = "declared_not_object_verified"
    created_at: AwareDatetime
    upload_expires_at: AwareDatetime
    processing_expires_at: AwareDatetime
    current_revision: OperatorChatImageRevisionResponse


class OperatorChatImageUploadsResponse(ClosedModel):
    account_id: UUID
    uploads: tuple[OperatorChatImageRootResponse, ...] = Field(
        max_length=OPERATOR_CHAT_IMAGE_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    anchor_created_at: AwareDatetime | None
    anchor_image_id: UUID | None
    observed_at: AwareDatetime
    pagination: Literal["anchored_search_not_commit_order"] = "anchored_search_not_commit_order"


class OperatorChatImageAttemptResponse(ClosedModel):
    id: UUID
    image_id: UUID
    number: int = Field(ge=1, le=MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS)
    started_at: AwareDatetime
    lease_until: AwareDatetime
    finished_at: AwareDatetime | None
    next_attempt_at: AwareDatetime | None
    outcome: OperatorChatImageAttemptOutcome
    failure: ChatImageFailure | None
    display_width: int | None
    display_height: int | None
    display_size: int | None
    display_sha256: str | None = Field(repr=False)


class OperatorChatImageMatchingOperationResponse(ClosedModel):
    id: UUID
    author_id: UUID
    conversation_id: UUID
    client_message_id: UUID
    state: MessageOutcome
    message_id: UUID | None
    cancelled_at: AwareDatetime | None


class OperatorChatImageHistoryResponse(ClosedModel):
    upload: OperatorChatImageRootResponse
    revisions: tuple[OperatorChatImageRevisionResponse, ...] = Field(
        max_length=OPERATOR_CHAT_IMAGE_PAGE_SIZE
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=1)
    observed_at: AwareDatetime
    attempts_current: tuple[OperatorChatImageAttemptResponse, ...] = Field(
        max_length=MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS, repr=False
    )
    attempt_observation: Literal["current_recorded_not_revision_time"] = (
        "current_recorded_not_revision_time"
    )
    matching_client_operation: OperatorChatImageMatchingOperationResponse | None
    operation_observation: Literal["current_matching_client_id_no_attachment_proof"] = (
        "current_matching_client_id_no_attachment_proof"
    )
    root_observation: Literal["current_recorded_not_revision_time"] = (
        "current_recorded_not_revision_time"
    )


def revision_response(value: OperatorChatImageUploadRevision) -> OperatorChatImageRevisionResponse:
    return OperatorChatImageRevisionResponse(
        image_id=value.image_id,
        account_id=value.account_id,
        conversation_id=value.conversation_id,
        client_message_id=value.client_message_id,
        version=value.version,
        state=value.state,
        updated_at=value.updated_at,
        attempt_id=value.attempt_id,
        ready_attempt_outcome=value.ready_attempt_outcome,
        failure=value.failure,
    )


def root_response(value: OperatorChatImageUploadRoot) -> OperatorChatImageRootResponse:
    return OperatorChatImageRootResponse(
        id=value.id,
        account_id=value.account_id,
        current_version=value.current_version,
        conversation_id=value.conversation_id,
        low_id=value.low_id,
        high_id=value.high_id,
        client_message_id=value.client_message_id,
        source_size=value.source_size,
        source_content_type=value.source_content_type,
        source_sha256=value.source_sha256.hex(),
        created_at=value.created_at,
        upload_expires_at=value.upload_expires_at,
        processing_expires_at=value.processing_expires_at,
        current_revision=revision_response(value.current_revision),
    )


def attempt_response(value: OperatorChatImageAttempt) -> OperatorChatImageAttemptResponse:
    return OperatorChatImageAttemptResponse(
        id=value.id,
        image_id=value.image_id,
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


def operation_response(
    value: OperatorChatImageMatchingOperation,
) -> OperatorChatImageMatchingOperationResponse:
    return OperatorChatImageMatchingOperationResponse(
        id=value.id,
        author_id=value.author_id,
        conversation_id=value.conversation_id,
        client_message_id=value.client_message_id,
        state=value.state,
        message_id=value.message_id,
        cancelled_at=value.cancelled_at,
    )


def chat_image_uploads_response(
    value: OperatorChatImageUploadsPage,
) -> OperatorChatImageUploadsResponse:
    return OperatorChatImageUploadsResponse(
        account_id=value.account_id,
        uploads=tuple(root_response(row) for row in value.uploads),
        next_cursor=value.next_cursor,
        anchor_created_at=value.anchor_created_at,
        anchor_image_id=value.anchor_image_id,
        observed_at=value.observed_at,
    )


def chat_image_history_response(
    value: OperatorChatImageHistoryPage,
) -> OperatorChatImageHistoryResponse:
    operation = value.matching_client_operation
    return OperatorChatImageHistoryResponse(
        upload=root_response(value.upload),
        revisions=tuple(revision_response(row) for row in value.revisions),
        next_cursor=value.next_cursor,
        anchor_version=value.anchor_version,
        observed_at=value.observed_at,
        attempts_current=tuple(attempt_response(row) for row in value.attempts_current),
        matching_client_operation=operation_response(operation) if operation is not None else None,
    )
