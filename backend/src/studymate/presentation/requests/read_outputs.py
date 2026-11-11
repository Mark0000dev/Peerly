from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from studymate.application.requests.query_ports import RequestDetail, RequestPage
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.limits import RequestLimits
from studymate.domain.requests.projections import (
    RequestObservation,
    RequestPeerState,
    RequestPublicState,
)
from studymate.presentation.requests.outputs import AcademicContextResponse, academic_context


class RequestCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    accept: bool
    decline: bool
    undo_decline: bool
    withdraw: bool
    view_profile: bool
    open_conversation: bool


class RequestPeerResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    person_id: UUID
    state: RequestPeerState
    display_name: str | None = Field(repr=False)
    photo_version: int | None


class RequestSummaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request_id: UUID
    version: int
    state: RequestPublicState
    mode: DiscoveryMode
    subject_id: UUID
    subject_label: str = Field(repr=False)
    topic: str | None = Field(repr=False)
    text: str = Field(repr=False)
    note: str | None = Field(repr=False)
    peer: RequestPeerResponse = Field(repr=False)
    sent_at: datetime
    expires_at: datetime
    observed_at: datetime
    unread: bool
    undo_until: datetime | None
    cooldown_until: datetime | None
    conversation_id: UUID | None
    capabilities: RequestCapabilitiesResponse


class RequestDetailResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: RequestSummaryResponse = Field(repr=False)
    text: str = Field(repr=False)
    note: str | None = Field(repr=False)
    context: AcademicContextResponse = Field(repr=False)
    disclosure_id: UUID
    disclosed_version: int
    disclosed_at: datetime


class RequestPageResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    requests: tuple[RequestSummaryResponse, ...] = Field(repr=False)
    next_cursor: str | None
    observed_at: datetime
    outgoing_pending: int
    successful_today: int
    unread_received: int
    outgoing_pending_limit: int
    daily_send_limit: int


def summary_response(value: RequestObservation) -> RequestSummaryResponse:
    request, capabilities = value.request, value.capabilities
    peer_id = (
        request.context.sender_id if value.box.value == "received" else request.context.recipient_id
    )
    goal = request.context.sender_goal or request.context.recipient_goal
    if goal is None:
        raise RuntimeError("Request summary lacks its retained academic goal")
    return RequestSummaryResponse(
        request_id=request.id,
        version=value.version,
        state=value.state,
        mode=request.context.mode,
        subject_id=request.context.subject_id,
        subject_label=goal.subject_label,
        topic=goal.goal.content.topic,
        text=request.message.text,
        note=request.message.note,
        peer=RequestPeerResponse(
            person_id=peer_id,
            state=value.peer.state,
            display_name=value.peer.display_name,
            photo_version=value.peer.photo_version,
        ),
        sent_at=request.sent_at,
        expires_at=request.expires_at,
        observed_at=value.observed_at,
        unread=value.unread,
        undo_until=value.undo_until,
        cooldown_until=value.cooldown_until,
        conversation_id=request.conversation_id,
        capabilities=RequestCapabilitiesResponse(
            accept=capabilities.can_accept,
            decline=capabilities.can_decline,
            undo_decline=capabilities.can_undo_decline,
            withdraw=capabilities.can_withdraw,
            view_profile=capabilities.can_view_profile,
            open_conversation=capabilities.can_open_conversation,
        ),
    )


def detail_response(value: RequestDetail) -> RequestDetailResponse:
    request = value.observation.request
    return RequestDetailResponse(
        request=summary_response(value.observation),
        text=request.message.text,
        note=request.message.note,
        context=academic_context(request.context),
        disclosure_id=value.disclosure.id,
        disclosed_version=value.disclosure.stored_version,
        disclosed_at=value.disclosure.created_at,
    )


def page_response(value: RequestPage, limits: RequestLimits) -> RequestPageResponse:
    return RequestPageResponse(
        requests=tuple(summary_response(row) for row in value.requests),
        next_cursor=value.next_cursor,
        observed_at=value.observed_at,
        outgoing_pending=value.quota.outgoing_pending,
        successful_today=value.quota.successful_today,
        unread_received=value.unread_received,
        outgoing_pending_limit=limits.outgoing_pending,
        daily_send_limit=limits.successful_per_day,
    )
