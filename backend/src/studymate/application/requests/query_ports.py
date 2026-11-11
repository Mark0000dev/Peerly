"""Bounded participant reads; authority comes from the authenticated transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.identity.sessions import IdentityReader
from studymate.application.requests.cursors import RequestCursor
from studymate.domain.requests.limits import SendQuota
from studymate.domain.requests.projections import (
    UNAVAILABLE_REQUEST_PEER,
    RequestBox,
    RequestListView,
    RequestObservation,
    RequestPeer,
    RequestVisibility,
)
from studymate.domain.requests.states import ConnectionRequest
from studymate.domain.requests.views import RequestDisclosure

REQUEST_PAGE_SIZE = 20


@dataclass(frozen=True, slots=True)
class RequestListQuery:
    actor_id: UUID
    box: RequestBox
    view: RequestListView
    as_of: datetime
    cursor: RequestCursor | None

    def __post_init__(self) -> None:
        if self.box == RequestBox.SENT and self.view == RequestListView.RECENTLY_DECLINED:
            raise ValueError("Recently declined is a received-only request view")


@dataclass(frozen=True, slots=True)
class RequestReadRow:
    request: ConnectionRequest = field(repr=False)
    visibility: RequestVisibility
    peer: RequestPeer = UNAVAILABLE_REQUEST_PEER


@dataclass(frozen=True, slots=True)
class RequestPage:
    requests: tuple[RequestObservation, ...] = field(repr=False)
    next_cursor: str | None
    observed_at: datetime
    quota: SendQuota
    unread_received: int


@dataclass(frozen=True, slots=True)
class RequestDetail:
    observation: RequestObservation = field(repr=False)
    disclosure: RequestDisclosure


class RequestQueryTransaction(IdentityReader, Protocol):
    async def list_requests(self, query: RequestListQuery) -> tuple[RequestReadRow, ...]:
        """Participant SQL filter before decode; at most20+lookahead; bulk current guards."""
        ...

    async def owned_request(self, actor_id: UUID, request_id: UUID) -> RequestReadRow | None:
        """Same unavailable result for foreign/unknown; scope SQL before private decoding."""
        ...

    async def quota(self, actor_id: UUID, at: datetime) -> SendQuota: ...

    async def unread_received(self, actor_id: UUID, at: datetime) -> int:
        """Actual total incoming effective-pending without any own explicit ACK."""
        ...

    async def disclose(self, source: RequestDisclosure) -> None:
        """Persist exact stored revision and original technical origin, never ACK/warm."""
        ...


class RequestQueryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[RequestQueryTransaction]: ...
