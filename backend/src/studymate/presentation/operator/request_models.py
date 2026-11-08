"""Closed raw retained request history, not participant eligibility or viewing authority."""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.operator.connection_requests import (
    OperatorRequestHistoryPage,
    OperatorRequestsPage,
)
from studymate.application.operator.request_ports import (
    OperatorRequestDirection,
    OperatorRequestFilters,
)
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.operator.connection_requests import (
    OPERATOR_REQUEST_ACKS_PER_REVISION,
    OPERATOR_REQUEST_PAGE_SIZE,
    OperatorRequestAcknowledgement,
    OperatorRequestOrigin,
    OperatorRequestPreview,
    OperatorRequestRevision,
    OperatorRequestRoot,
)
from studymate.domain.requests.states import RequestState
from studymate.presentation.operator.models import ClosedModel


class OperatorRequestsQuery(ClosedModel):
    peer_id: UUID | None = None
    direction: OperatorRequestDirection | None = None
    mode: DiscoveryMode | None = None
    state: RequestState | None = None
    sent_from: AwareDatetime | None = None
    sent_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorRequestFilters:
        return OperatorRequestFilters(
            self.peer_id, self.direction, self.mode, self.state, self.sent_from, self.sent_before
        )

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class OperatorRequestHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class OperatorRequestOriginResponse(ClosedModel):
    http_request_id: UUID | None
    action_id: UUID | None
    trace_id: str | None = Field(max_length=32, repr=False)
    span_id: str | None = Field(max_length=16, repr=False)
    representation: Literal["raw_recorded_source_correlation"] = "raw_recorded_source_correlation"


class OperatorRequestRootResponse(ClosedModel):
    id: UUID
    relationship_id: UUID
    sender_id: UUID
    recipient_id: UUID
    preview_id: UUID
    mode: DiscoveryMode
    subject_id: UUID
    sent_at: AwareDatetime
    expires_at: AwareDatetime
    current_version: int = Field(ge=1)
    state: RequestState
    origin: OperatorRequestOriginResponse


class OperatorRequestsResponse(ClosedModel):
    account_id: UUID
    requests: tuple[OperatorRequestRootResponse, ...] = Field(max_length=OPERATOR_REQUEST_PAGE_SIZE)
    next_cursor: str | None
    anchor_sent_at: AwareDatetime | None
    anchor_request_id: UUID | None
    observed_at: AwareDatetime
    pagination: Literal["anchored_search_not_commit_order"] = "anchored_search_not_commit_order"


class OperatorRequestPreviewResponse(ClosedModel):
    id: UUID
    sender_id: UUID
    recipient_id: UUID
    mode: DiscoveryMode
    subject_id: UUID
    created_at: AwareDatetime
    source_json_raw: str = Field(repr=False)
    sender_goal_id: UUID | None
    sender_goal_version: int | None
    recipient_goal_id: UUID | None
    recipient_goal_version: int | None
    sender_help_version: int | None
    recipient_help_version: int | None
    representation: Literal["raw_stored_json_object_not_current_request_schema"] = (
        "raw_stored_json_object_not_current_request_schema"
    )


class OperatorRequestRevisionResponse(ClosedModel):
    request_id: UUID
    version: int = Field(ge=1)
    state: RequestState
    changed_at: AwareDatetime
    decline_until: AwareDatetime | None
    conversation_id: UUID | None


class OperatorRequestDisclosureResponse(ClosedModel):
    id: UUID
    viewer_id: UUID
    request_id: UUID
    stored_version: int = Field(ge=1)
    created_at: AwareDatetime
    origin: OperatorRequestOriginResponse


class OperatorRequestAcknowledgementResponse(ClosedModel):
    id: UUID
    viewer_id: UUID
    request_id: UUID
    stored_version: int = Field(ge=1)
    acknowledged_at: AwareDatetime
    origin: OperatorRequestOriginResponse
    disclosure: OperatorRequestDisclosureResponse


class OperatorRequestHistoryResponse(ClosedModel):
    request: OperatorRequestRootResponse
    request_text: str = Field(repr=False)
    note: str | None = Field(repr=False)
    preview: OperatorRequestPreviewResponse = Field(repr=False)
    revisions: tuple[OperatorRequestRevisionResponse, ...] = Field(
        max_length=OPERATOR_REQUEST_PAGE_SIZE
    )
    acknowledgements: tuple[OperatorRequestAcknowledgementResponse, ...] = Field(
        max_length=OPERATOR_REQUEST_PAGE_SIZE * OPERATOR_REQUEST_ACKS_PER_REVISION
    )
    next_cursor: str | None
    anchor_version: int = Field(ge=1)
    observed_at: AwareDatetime
    root_observation: Literal["current_recorded_not_revision_snapshot"] = (
        "current_recorded_not_revision_snapshot"
    )
    ack_scope: Literal["page_revisions_only"] = "page_revisions_only"
    disclosure_scope: Literal["ack_linked_disclosures_not_all_views"] = (
        "ack_linked_disclosures_not_all_views"
    )


def origin_response(value: OperatorRequestOrigin) -> OperatorRequestOriginResponse:
    return OperatorRequestOriginResponse(
        http_request_id=value.http_request_id,
        action_id=value.action_id,
        trace_id=value.trace_id,
        span_id=value.span_id,
    )


def root_response(value: OperatorRequestRoot) -> OperatorRequestRootResponse:
    return OperatorRequestRootResponse(
        id=value.id,
        relationship_id=value.relationship_id,
        sender_id=value.sender_id,
        recipient_id=value.recipient_id,
        preview_id=value.preview_id,
        mode=value.mode,
        subject_id=value.subject_id,
        sent_at=value.sent_at,
        expires_at=value.expires_at,
        current_version=value.current_version,
        state=value.state,
        origin=origin_response(value.origin),
    )


def preview_response(value: OperatorRequestPreview) -> OperatorRequestPreviewResponse:
    return OperatorRequestPreviewResponse(
        id=value.id,
        sender_id=value.sender_id,
        recipient_id=value.recipient_id,
        mode=value.mode,
        subject_id=value.subject_id,
        created_at=value.created_at,
        source_json_raw=value.source_json_raw,
        sender_goal_id=value.sender_goal_id,
        sender_goal_version=value.sender_goal_version,
        recipient_goal_id=value.recipient_goal_id,
        recipient_goal_version=value.recipient_goal_version,
        sender_help_version=value.sender_help_version,
        recipient_help_version=value.recipient_help_version,
    )


def revision_response(value: OperatorRequestRevision) -> OperatorRequestRevisionResponse:
    return OperatorRequestRevisionResponse(
        request_id=value.request_id,
        version=value.version,
        state=value.state,
        changed_at=value.changed_at,
        decline_until=value.decline_until,
        conversation_id=value.conversation_id,
    )


def acknowledgement_response(
    value: OperatorRequestAcknowledgement,
) -> OperatorRequestAcknowledgementResponse:
    disclosure = value.disclosure
    return OperatorRequestAcknowledgementResponse(
        id=value.id,
        viewer_id=value.viewer_id,
        request_id=value.request_id,
        stored_version=value.stored_version,
        acknowledged_at=value.acknowledged_at,
        origin=origin_response(value.origin),
        disclosure=OperatorRequestDisclosureResponse(
            id=disclosure.id,
            viewer_id=disclosure.viewer_id,
            request_id=disclosure.request_id,
            stored_version=disclosure.stored_version,
            created_at=disclosure.created_at,
            origin=origin_response(disclosure.origin),
        ),
    )


def requests_response(value: OperatorRequestsPage) -> OperatorRequestsResponse:
    return OperatorRequestsResponse(
        account_id=value.account_id,
        requests=tuple(root_response(row) for row in value.requests),
        next_cursor=value.next_cursor,
        anchor_sent_at=value.anchor_sent_at,
        anchor_request_id=value.anchor_request_id,
        observed_at=value.observed_at,
    )


def request_history_response(value: OperatorRequestHistoryPage) -> OperatorRequestHistoryResponse:
    snapshot = value.snapshot
    return OperatorRequestHistoryResponse(
        request=root_response(snapshot.root),
        request_text=snapshot.request_text,
        note=snapshot.note,
        preview=preview_response(snapshot.preview),
        revisions=tuple(revision_response(row) for row in value.revisions),
        acknowledgements=tuple(acknowledgement_response(row) for row in value.acknowledgements),
        next_cursor=value.next_cursor,
        anchor_version=value.anchor_version,
        observed_at=value.observed_at,
    )
