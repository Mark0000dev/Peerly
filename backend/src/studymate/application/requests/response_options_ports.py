"""One recipient-scoped, no-write source read; no public-profile grant from snapshots."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from studymate.application.discovery.profiles import DiscoveryProfileSource
from studymate.application.identity.sessions import IdentityReader
from studymate.domain.requests.states import ConnectionRequest


@dataclass(frozen=True, slots=True)
class ResponseOptionsContext:
    request: ConnectionRequest = field(repr=False)
    own: DiscoveryProfileSource = field(repr=False)
    peer: DiscoveryProfileSource = field(repr=False)
    blocked: bool


class ResponseOptionsTransaction(IdentityReader, Protocol):
    async def response_context(
        self, actor_id: UUID, request_id: UUID
    ) -> ResponseOptionsContext | None:
        """Scope recipient/pending/deadline first; no ACK, disclosure or activity writes."""
        ...


class ResponseOptionsUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ResponseOptionsTransaction]: ...
