"""Closed raw feedback source DTOs; references are evidence, never disclosure grants."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.operator.feedback_ports import (
    OperatorFeedbackDirection,
    OperatorFeedbackFilters,
)
from studymate.application.operator.peer_feedback import (
    OperatorFeedbackHistoryPage,
    OperatorFeedbackRemovalsPage,
    OperatorFeedbackRootsPage,
)
from studymate.domain.operator.peer_feedback import (
    MAX_OPERATOR_FEEDBACK_DESCRIPTORS,
    MAX_OPERATOR_FEEDBACK_TEXT,
    OPERATOR_FEEDBACK_PAGE_SIZE,
    OperatorFeedbackRemoval,
    OperatorFeedbackRevision,
    OperatorFeedbackRoot,
)
from studymate.presentation.operator.models import ClosedModel
from studymate.presentation.operator.timeline_models import (
    OperatorEventOriginResponse,
    origin_response,
)


class OperatorFeedbackQuery(ClosedModel):
    peer_id: UUID | None = None
    direction: OperatorFeedbackDirection | None = None
    removed: bool | None = None
    changed_from: AwareDatetime | None = None
    changed_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorFeedbackFilters:
        return OperatorFeedbackFilters(
            self.peer_id, self.direction, self.removed, self.changed_from, self.changed_before
        )

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class OperatorFeedbackChildQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorFeedbackRootResponse(ClosedModel):
    id: UUID
    reviewer_id: UUID
    partner_id: UUID
    conversation_id: UUID
    low_id: UUID
    high_id: UUID
    current_version: int = Field(ge=1)
    current_removal_id: UUID | None
    current_changed_at: AwareDatetime
    removal_reference: Literal["pointer_not_all_history"] = "pointer_not_all_history"


class OperatorFeedbackRootsResponse(ClosedModel):
    account_id: UUID
    feedback: tuple[OperatorFeedbackRootResponse, ...] = Field(
        max_length=OPERATOR_FEEDBACK_PAGE_SIZE
    )
    next_cursor: str | None
    anchor_changed_at: AwareDatetime | None
    anchor_feedback_id: UUID | None
    observed_at: AwareDatetime
    pagination: Literal["current_pointer_anchored_search_not_creation_or_commit_snapshot"] = (
        "current_pointer_anchored_search_not_creation_or_commit_snapshot"
    )


class OperatorFeedbackRevisionResponse(ClosedModel):
    feedback_id: UUID
    version: int = Field(ge=1)
    conversation_id: UUID
    reviewer_id: UUID
    partner_id: UUID
    low_id: UUID
    high_id: UUID
    worked_confirmation_id: UUID
    worked_answer: str = Field(max_length=20)
    low_message_id: UUID | None
    high_message_id: UUID | None
    again: str = Field(max_length=5)
    descriptors: tuple[str, ...] = Field(max_length=MAX_OPERATOR_FEEDBACK_DESCRIPTORS)
    team_note: str | None = Field(max_length=MAX_OPERATOR_FEEDBACK_TEXT, repr=False)
    changed_at: AwareDatetime
    origin: OperatorEventOriginResponse
    representation: Literal["raw_recorded_feedback_not_current_content_decoder"] = (
        "raw_recorded_feedback_not_current_content_decoder"
    )


class OperatorFeedbackHistoryResponse(ClosedModel):
    feedback: OperatorFeedbackRootResponse
    revisions: tuple[OperatorFeedbackRevisionResponse, ...] = Field(
        max_length=OPERATOR_FEEDBACK_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=1)
    observed_at: AwareDatetime
    root_observation: Literal["current_recorded_not_revision_snapshot"] = (
        "current_recorded_not_revision_snapshot"
    )


class OperatorFeedbackRemovalResponse(ClosedModel):
    id: UUID
    feedback_id: UUID
    source_version: int = Field(ge=1)
    operator_id: UUID
    operator_access_version: int = Field(ge=1)
    operator_access_active: bool
    kind: str = Field(max_length=12)
    reason: str = Field(min_length=1, max_length=MAX_OPERATOR_FEEDBACK_TEXT, repr=False)
    removed_at: AwareDatetime
    origin: OperatorEventOriginResponse


class OperatorFeedbackRemovalsResponse(ClosedModel):
    feedback: OperatorFeedbackRootResponse
    removals: tuple[OperatorFeedbackRemovalResponse, ...] = Field(
        max_length=OPERATOR_FEEDBACK_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    anchor_removed_at: AwareDatetime | None
    anchor_removal_id: UUID | None
    observed_at: AwareDatetime
    pagination: Literal["anchored_search_not_commit_order"] = "anchored_search_not_commit_order"
    root_observation: Literal["current_recorded_not_revision_snapshot"] = (
        "current_recorded_not_revision_snapshot"
    )


def root_response(row: OperatorFeedbackRoot) -> OperatorFeedbackRootResponse:
    return OperatorFeedbackRootResponse(
        id=row.id,
        reviewer_id=row.reviewer_id,
        partner_id=row.partner_id,
        conversation_id=row.conversation_id,
        low_id=row.low_id,
        high_id=row.high_id,
        current_version=row.current_version,
        current_removal_id=row.current_removal_id,
        current_changed_at=row.current_changed_at,
    )


def revision_response(row: OperatorFeedbackRevision) -> OperatorFeedbackRevisionResponse:
    return OperatorFeedbackRevisionResponse(
        feedback_id=row.feedback_id,
        version=row.version,
        conversation_id=row.conversation_id,
        reviewer_id=row.reviewer_id,
        partner_id=row.partner_id,
        low_id=row.low_id,
        high_id=row.high_id,
        worked_confirmation_id=row.worked_confirmation_id,
        worked_answer=row.worked_answer,
        low_message_id=row.low_message_id,
        high_message_id=row.high_message_id,
        again=row.again,
        descriptors=row.descriptors,
        team_note=row.team_note,
        changed_at=row.changed_at,
        origin=origin_response(row.origin),
    )


def removal_response(row: OperatorFeedbackRemoval) -> OperatorFeedbackRemovalResponse:
    return OperatorFeedbackRemovalResponse(
        id=row.id,
        feedback_id=row.feedback_id,
        source_version=row.source_version,
        operator_id=row.operator_id,
        operator_access_version=row.operator_access_version,
        operator_access_active=row.operator_access_active,
        kind=row.kind,
        reason=row.reason,
        removed_at=row.removed_at,
        origin=origin_response(row.origin),
    )


def feedback_roots_response(page: OperatorFeedbackRootsPage) -> OperatorFeedbackRootsResponse:
    return OperatorFeedbackRootsResponse(
        account_id=page.account_id,
        feedback=tuple(root_response(row) for row in page.feedback),
        next_cursor=page.next_cursor,
        anchor_changed_at=page.anchor_changed_at,
        anchor_feedback_id=page.anchor_feedback_id,
        observed_at=page.observed_at,
    )


def feedback_history_response(page: OperatorFeedbackHistoryPage) -> OperatorFeedbackHistoryResponse:
    return OperatorFeedbackHistoryResponse(
        feedback=root_response(page.root),
        revisions=tuple(revision_response(row) for row in page.revisions),
        next_cursor=page.next_cursor,
        anchor_version=page.anchor_version,
        observed_at=page.observed_at,
    )


def feedback_removals_response(
    page: OperatorFeedbackRemovalsPage,
) -> OperatorFeedbackRemovalsResponse:
    return OperatorFeedbackRemovalsResponse(
        feedback=root_response(page.root),
        removals=tuple(removal_response(row) for row in page.removals),
        next_cursor=page.next_cursor,
        anchor_removed_at=page.anchor_removed_at,
        anchor_removal_id=page.anchor_removal_id,
        observed_at=page.observed_at,
    )
