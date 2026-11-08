"""Actor-relative observations; effective deadlines never fabricate stored versions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.requests.states import (
    ConnectionRequest,
    RequestState,
    RequestUnavailableError,
)
from studymate.domain.time import require_aware


class RequestBox(StrEnum):
    RECEIVED = "received"
    SENT = "sent"


class RequestListView(StrEnum):
    ACTIVE = "active"
    HISTORY = "history"
    RECENTLY_DECLINED = "recently_declined"


class RequestPublicState(StrEnum):
    PENDING = "pending"
    PENDING_DECLINE = "pending_decline"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    CLOSED = "closed"


class RequestPeerState(StrEnum):
    PUBLIC = "public"
    UNAVAILABLE = "unavailable"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class RequestPeer:
    state: RequestPeerState
    display_name: str | None = field(default=None, repr=False)
    photo_version: int | None = None


UNAVAILABLE_REQUEST_PEER = RequestPeer(RequestPeerState.UNAVAILABLE)


@dataclass(frozen=True, slots=True)
class RequestCapabilities:
    can_accept: bool
    can_decline: bool
    can_undo_decline: bool
    can_withdraw: bool
    can_view_profile: bool
    can_open_conversation: bool


@dataclass(frozen=True, slots=True)
class RequestVisibility:
    acknowledged: bool
    contact_allowed: bool
    public_profile_allowed: bool


@dataclass(frozen=True, slots=True)
class RequestObservation:
    request: ConnectionRequest = field(repr=False)
    box: RequestBox
    state: RequestPublicState
    observed_at: datetime
    unread: bool
    undo_until: datetime | None
    cooldown_until: datetime | None
    capabilities: RequestCapabilities
    peer: RequestPeer = UNAVAILABLE_REQUEST_PEER

    @property
    def version(self) -> int:
        return self.request.version


def request_box(request: ConnectionRequest, viewer_id: UUID) -> RequestBox:
    if viewer_id == request.context.sender_id:
        return RequestBox.SENT
    if viewer_id == request.context.recipient_id:
        return RequestBox.RECEIVED
    raise RequestUnavailableError


def in_request_view(request: ConnectionRequest, view: RequestListView, at: datetime) -> bool:
    effective = request.effective(at)
    if view == RequestListView.RECENTLY_DECLINED:
        return effective.state == RequestState.PENDING_DECLINE
    active = effective.pending or effective.state == RequestState.ACCEPTED
    return active if view == RequestListView.ACTIVE else not active


def observe_request(
    request: ConnectionRequest,
    viewer_id: UUID,
    at: datetime,
    visibility: RequestVisibility,
    peer: RequestPeer = UNAVAILABLE_REQUEST_PEER,
) -> RequestObservation:
    require_aware(at)
    box = request_box(request, viewer_id)
    incoming = box == RequestBox.RECEIVED
    effective = request.effective(at)
    state = effective.state
    public_state = RequestPublicState.CLOSED
    if state == RequestState.PENDING or (state == RequestState.PENDING_DECLINE and not incoming):
        public_state = RequestPublicState.PENDING
    elif state == RequestState.PENDING_DECLINE:
        public_state = RequestPublicState.PENDING_DECLINE
    elif state == RequestState.ACCEPTED:
        public_state = RequestPublicState.ACCEPTED
    elif state == RequestState.DECLINED and incoming:
        public_state = RequestPublicState.DECLINED
    elif state == RequestState.WITHDRAWN and not incoming:
        public_state = RequestPublicState.WITHDRAWN
    elif state == RequestState.EXPIRED:
        public_state = RequestPublicState.EXPIRED
    caps = RequestCapabilities(
        can_accept=incoming and state == RequestState.PENDING and visibility.contact_allowed,
        can_decline=incoming and state == RequestState.PENDING,
        can_undo_decline=incoming
        and state == RequestState.PENDING_DECLINE
        and visibility.contact_allowed,
        can_withdraw=not incoming and effective.pending,
        can_view_profile=visibility.public_profile_allowed,
        can_open_conversation=state == RequestState.ACCEPTED
        and effective.conversation_id is not None,
    )
    return RequestObservation(
        request,
        box,
        public_state,
        at,
        unread=incoming and state == RequestState.PENDING and not visibility.acknowledged,
        undo_until=request.decline_until
        if incoming and state == RequestState.PENDING_DECLINE
        else None,
        cooldown_until=effective.sender_cooldown_until
        if not incoming and state == RequestState.WITHDRAWN
        else None,
        capabilities=caps,
        peer=peer,
    )
