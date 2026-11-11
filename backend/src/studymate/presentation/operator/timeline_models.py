"""Bounded closed operator timeline DTOs, with exact finite metadata/source columns."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.operator.timeline import OperatorEventsPage
from studymate.application.operator.timeline_ports import OperatorEventFilters
from studymate.domain.ai.jobs import Failure, JobState
from studymate.domain.ai.tasks import AiKind
from studymate.domain.feedback.assessments import StudyAgain
from studymate.domain.feedback.outcomes import StudyAnswer
from studymate.domain.lifecycle.states import LifecycleOperation
from studymate.domain.messaging import MessageOutcome
from studymate.domain.operator.audit import (
    OPERATOR_EVENT_PAGE_SIZE,
    OperatorAction,
    OperatorAuditOutcome,
    OperatorResourceKind,
)
from studymate.domain.operator.chat_media import OperatorChatMediaKind
from studymate.domain.operator.profile_media import OperatorProfileMediaKind
from studymate.domain.operator.timeline import (
    MAX_EVENT_SOURCE_REFS,
    OperatorAuditDetail,
    OperatorEventKind,
    OperatorEventOrigin,
    OperatorSourceKind,
    OperatorTimelineEvent,
)
from studymate.domain.profiles import OnboardingTask
from studymate.domain.requests.states import RequestState
from studymate.presentation.operator.models import ClosedModel


class OperatorEventQuery(ClosedModel):
    subject_account_id: UUID | None = None
    http_request_id: UUID | None = None
    action_id: UUID | None = None
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$", repr=False)
    kind: OperatorEventKind | None = None
    occurred_from: AwareDatetime | None = None
    occurred_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorEventFilters:
        return OperatorEventFilters(
            self.subject_account_id,
            self.http_request_id,
            self.action_id,
            self.trace_id,
            self.kind,
            self.occurred_from,
            self.occurred_before,
        )

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class OperatorEventOriginResponse(ClosedModel):
    http_request_id: UUID | None
    action_id: UUID | None
    trace_id: str | None = Field(pattern=r"^[0-9a-f]{32}$")
    span_id: str | None = Field(pattern=r"^[0-9a-f]{16}$")


class OperatorEventSourceResponse(ClosedModel):
    kind: OperatorSourceKind
    id: UUID
    owner_id: UUID | None
    version: int | None = Field(ge=1)
    conversation_id: UUID | None
    related_account_id: UUID | None
    operator_access_version: int | None = Field(ge=1)


class OperatorEventFactsResponse(ClosedModel):
    topic_present: bool | None
    shared_learning: bool | None
    onboarding_task: OnboardingTask | None
    ai_kind: AiKind | None
    ai_state: JobState | None
    ai_reason: Failure | None
    blocked: bool | None
    passed: bool | None
    request_state: RequestState | None
    message_state: MessageOutcome | None
    study_answer: StudyAnswer | None
    feedback_again: StudyAgain | None
    operator_action: OperatorAction | None
    lifecycle_operation: LifecycleOperation | None


class OperatorEventResponse(ClosedModel):
    id: UUID
    subject_account_id: UUID
    kind: OperatorEventKind
    schema_version: Literal[1] = 1
    occurred_at: datetime
    sources: tuple[OperatorEventSourceResponse, ...] = Field(
        min_length=1, max_length=MAX_EVENT_SOURCE_REFS
    )
    facts: OperatorEventFactsResponse
    origin: OperatorEventOriginResponse
    initiator_account_id: UUID | None


class OperatorEventsResponse(ClosedModel):
    events: tuple[OperatorEventResponse, ...] = Field(max_length=OPERATOR_EVENT_PAGE_SIZE)
    next_cursor: str | None = Field(max_length=1024, repr=False)
    search_anchor_at: datetime
    pagination: Literal["anchored_search_not_commit_order"] = "anchored_search_not_commit_order"


class OperatorAuditResultRefResponse(ClosedModel):
    kind: OperatorResourceKind
    id: UUID


class OperatorAuditDetailResponse(ClosedModel):
    id: UUID
    operator_id: UUID
    operator_access_version: int = Field(ge=1)
    operator_access_changed_at: datetime
    action: OperatorAction
    requested_kind: OperatorResourceKind | None
    requested_id: UUID | None
    results: tuple[OperatorAuditResultRefResponse, ...] = Field(max_length=OPERATOR_EVENT_PAGE_SIZE)
    occurred_at: datetime
    outcome: OperatorAuditOutcome
    query_fingerprinted: bool
    origin: OperatorEventOriginResponse
    requested_media_owner_id: UUID | None
    requested_media_attempt_id: UUID | None
    requested_media_kind: OperatorProfileMediaKind | None
    actual_source_upload_id: UUID | None
    requested_chat_owner_id: UUID | None
    requested_chat_attempt_id: UUID | None
    requested_chat_kind: OperatorChatMediaKind | None
    actual_source_image_id: UUID | None


def origin_response(value: OperatorEventOrigin) -> OperatorEventOriginResponse:
    return OperatorEventOriginResponse(
        http_request_id=value.http_request_id,
        action_id=value.action_id,
        trace_id=value.trace_id,
        span_id=value.span_id,
    )


def event_response(value: OperatorTimelineEvent) -> OperatorEventResponse:
    facts = value.facts
    return OperatorEventResponse(
        id=value.id,
        subject_account_id=value.subject_account_id,
        kind=value.kind,
        occurred_at=value.occurred_at,
        sources=tuple(
            OperatorEventSourceResponse(
                kind=source.kind,
                id=source.id,
                owner_id=source.owner_id,
                version=source.version,
                conversation_id=source.conversation_id,
                related_account_id=source.related_account_id,
                operator_access_version=source.operator_access_version,
            )
            for source in value.sources
        ),
        facts=OperatorEventFactsResponse(
            topic_present=facts.topic_present,
            shared_learning=facts.shared_learning,
            onboarding_task=facts.onboarding_task,
            ai_kind=facts.ai_kind,
            ai_state=facts.ai_state,
            ai_reason=facts.ai_reason,
            blocked=facts.blocked,
            passed=facts.passed,
            request_state=facts.request_state,
            message_state=facts.message_state,
            study_answer=facts.study_answer,
            feedback_again=facts.feedback_again,
            operator_action=facts.operator_action,
            lifecycle_operation=facts.lifecycle_operation,
        ),
        origin=origin_response(value.origin),
        initiator_account_id=value.initiator_account_id,
    )


def events_response(value: OperatorEventsPage) -> OperatorEventsResponse:
    return OperatorEventsResponse(
        events=tuple(event_response(row) for row in value.events),
        next_cursor=value.next_cursor,
        search_anchor_at=value.search_anchor_at,
    )


def audit_response(value: OperatorAuditDetail) -> OperatorAuditDetailResponse:
    audit = value.audit
    return OperatorAuditDetailResponse(
        id=audit.id,
        operator_id=audit.access.account_id,
        operator_access_version=audit.access.version,
        operator_access_changed_at=audit.access.changed_at,
        action=audit.action,
        requested_kind=audit.requested.kind if audit.requested is not None else None,
        requested_id=audit.requested.id if audit.requested is not None else None,
        results=tuple(
            OperatorAuditResultRefResponse(kind=ref.kind, id=ref.id) for ref in audit.results
        ),
        occurred_at=audit.at,
        outcome=audit.outcome,
        query_fingerprinted=audit.query_fingerprint is not None,
        requested_media_owner_id=audit.media_request.account_id
        if audit.media_request is not None
        else None,
        requested_media_attempt_id=audit.media_request.attempt_id
        if audit.media_request is not None
        else None,
        requested_media_kind=audit.media_request.kind if audit.media_request is not None else None,
        actual_source_upload_id=audit.actual_source_upload_id,
        requested_chat_owner_id=audit.chat_media_request.account_id
        if audit.chat_media_request
        else None,
        requested_chat_attempt_id=audit.chat_media_request.attempt_id
        if audit.chat_media_request
        else None,
        requested_chat_kind=audit.chat_media_request.kind if audit.chat_media_request else None,
        actual_source_image_id=audit.actual_source_image_id,
        origin=origin_response(value.origin),
    )
