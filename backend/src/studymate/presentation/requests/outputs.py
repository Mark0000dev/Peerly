"""Explicit request academic fields; no ORM, private storage refs or authority tokens."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from studymate.application.requests.ports import (
    AcceptedRequest,
    AlreadyConnected,
    ExistingOutgoing,
    IncomingRequestExists,
    SentRequest,
)
from studymate.application.requests.preview_checks import CheckedRequestPreview, PreviewBlockReason
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import GoalSnapshot, HelpSnapshot, RequestContext
from studymate.domain.requests.states import ConnectionRequest, RequestState
from studymate.domain.requests.suggestions import suggested_request_text
from studymate.domain.requests.views import RequestViewReceipt


class GoalContextResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    owner_id: UUID
    goal_id: UUID
    version: int
    subject_id: UUID
    subject_label: str
    topic: str | None = Field(repr=False)
    context: str | None = Field(repr=False)
    shared_learning: bool


class HelpContextResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    owner_id: UUID
    version: int
    subject_id: UUID
    subject_label: str
    topic_note: str | None = Field(repr=False)


class AcademicContextResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    mode: DiscoveryMode
    sender_goal: GoalContextResponse | None = Field(repr=False)
    recipient_goal: GoalContextResponse | None = Field(repr=False)
    sender_help: HelpContextResponse | None = Field(repr=False)
    recipient_help: HelpContextResponse | None = Field(repr=False)


def goal_context(value: GoalSnapshot | None, subject_id: UUID) -> GoalContextResponse | None:
    if value is None:
        return None
    goal = value.goal
    return GoalContextResponse(
        owner_id=goal.account_id,
        goal_id=goal.id,
        version=goal.version,
        subject_id=subject_id,
        subject_label=value.subject_label,
        topic=goal.content.topic,
        context=goal.content.context,
        shared_learning=goal.content.shared_learning,
    )


def help_context(value: HelpSnapshot | None, subject_id: UUID) -> HelpContextResponse | None:
    if value is None:
        return None
    for item, label in zip(value.revision.subjects.values, value.labels, strict=True):
        if item.subject_id == subject_id:
            return HelpContextResponse(
                owner_id=value.revision.account_id,
                version=value.revision.version,
                subject_id=subject_id,
                subject_label=label,
                topic_note=item.topic_note,
            )
    raise RuntimeError("Request academic context lost its declared subject")


def academic_context(value: RequestContext) -> AcademicContextResponse:
    return AcademicContextResponse(
        mode=value.mode,
        sender_goal=goal_context(value.sender_goal, value.subject_id),
        recipient_goal=goal_context(value.recipient_goal, value.subject_id),
        sender_help=help_context(value.sender_help, value.subject_id),
        recipient_help=help_context(value.recipient_help, value.subject_id),
    )


class RequestMutationResponse(BaseModel):
    """Original action receipt; no claim that these are current live capabilities."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: Literal[
        "sent", "existing_outgoing", "incoming", "accepted", "declined", "undo_decline", "withdrawn"
    ]
    request_id: UUID
    version: int
    changed_at: datetime
    conversation_id: UUID | None
    undo_until: datetime | None


class ConnectedResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: Literal["connected"] = "connected"
    request_id: UUID
    conversation_id: UUID


class PreviewQuotaResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outgoing_pending: int = Field(ge=0)
    successful_today: int = Field(ge=0)
    outgoing_pending_limit: int = Field(ge=1)
    daily_send_limit: int = Field(ge=1)
    reset_at: datetime
    outgoing_pending_remaining: int = Field(ge=0)
    daily_sends_remaining: int = Field(ge=0)


class PreviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: Literal["preview"] = "preview"
    preview_id: UUID
    created_at: datetime
    context: AcademicContextResponse = Field(repr=False)
    suggested_text: str = Field(min_length=1, max_length=240, repr=False)
    checked_at: datetime
    quota: PreviewQuotaResponse
    can_send: bool
    block_reason: PreviewBlockReason | None
    cooldown_until: datetime | None

    @model_validator(mode="after")
    def consistent_availability(self) -> Self:
        if self.can_send != (self.block_reason is None):
            raise ValueError("Preview sendability must agree with its checked reason")
        if (self.block_reason == PreviewBlockReason.COOLDOWN) != (self.cooldown_until is not None):
            raise ValueError("Only cooldown results expose a cooldown deadline")
        return self


class ViewedResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    acknowledgement_id: UUID
    request_id: UUID
    stored_version: int
    disclosure_id: UUID
    acknowledged_at: datetime


def viewed_response(value: RequestViewReceipt) -> ViewedResponse:
    return ViewedResponse(
        acknowledgement_id=value.id,
        request_id=value.request_id,
        stored_version=value.stored_version,
        disclosure_id=value.disclosure_id,
        acknowledged_at=value.acknowledged_at,
    )


def mutation_response(
    value: ConnectionRequest,
    outcome: Literal[
        "sent", "existing_outgoing", "incoming", "accepted", "declined", "undo_decline", "withdrawn"
    ],
) -> RequestMutationResponse:
    return RequestMutationResponse(
        outcome=outcome,
        request_id=value.id,
        version=value.version,
        changed_at=value.changed_at,
        conversation_id=value.conversation_id,
        undo_until=value.decline_until
        if value.state == RequestState.PENDING_DECLINE and outcome == "declined"
        else None,
    )


def send_response(
    value: SentRequest | ExistingOutgoing | IncomingRequestExists | AlreadyConnected,
) -> RequestMutationResponse | ConnectedResponse:
    if isinstance(value, AlreadyConnected):
        return ConnectedResponse(
            request_id=value.conversation.request_id, conversation_id=value.conversation.id
        )
    if isinstance(value, ExistingOutgoing):
        return mutation_response(value.request, "existing_outgoing")
    if isinstance(value, IncomingRequestExists):
        return mutation_response(value.request, "incoming")
    return mutation_response(value.request, "sent")


def preview_response(
    value: CheckedRequestPreview | ExistingOutgoing | IncomingRequestExists | AlreadyConnected,
) -> PreviewResponse | RequestMutationResponse | ConnectedResponse:
    if not isinstance(value, CheckedRequestPreview):
        return send_response(value)
    preview, check = value.preview, value.check
    return PreviewResponse(
        preview_id=preview.id,
        created_at=preview.created_at,
        context=academic_context(preview.context),
        suggested_text=suggested_request_text(preview.context),
        checked_at=check.checked_at,
        quota=PreviewQuotaResponse(
            outgoing_pending=check.quota.outgoing_pending,
            successful_today=check.quota.successful_today,
            outgoing_pending_limit=check.limits.outgoing_pending,
            daily_send_limit=check.limits.successful_per_day,
            reset_at=check.reset_at,
            outgoing_pending_remaining=max(
                0, check.limits.outgoing_pending - check.quota.outgoing_pending
            ),
            daily_sends_remaining=max(
                0, check.limits.successful_per_day - check.quota.successful_today
            ),
        ),
        can_send=check.can_send,
        block_reason=check.block_reason,
        cooldown_until=check.cooldown_until,
    )


def accepted_response(value: AcceptedRequest) -> RequestMutationResponse:
    return mutation_response(value.request, "accepted")
