from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.discovery.profiles import DiscoveryProfileReader
from studymate.application.idempotency import IntentKey
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.context import RequestContext
from studymate.domain.requests.limits import SendQuota
from studymate.domain.requests.states import ConnectionRequest


class RequestSourceChangedError(Exception):
    pass


class RequestCooldownError(Exception):
    def __init__(self, until: datetime) -> None:
        super().__init__("Request sender is cooling down")
        self.until = until


class RequestVersionConflictError(Exception):
    def __init__(self, version: int) -> None:
        super().__init__("Request revision has changed")
        self.current_version = version


@dataclass(frozen=True, slots=True)
class RequestPreview:
    id: UUID
    context: RequestContext = field(repr=False)
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationReference:
    """Actual unique conversation/source fact supplied by the shared foundation."""

    id: UUID
    relationship_id: UUID
    pair: AccountPair
    request_id: UUID


@dataclass(frozen=True, slots=True)
class SentRequest:
    request: ConnectionRequest = field(repr=False)


@dataclass(frozen=True, slots=True)
class ExistingOutgoing:
    request: ConnectionRequest = field(repr=False)


@dataclass(frozen=True, slots=True)
class IncomingRequestExists:
    request: ConnectionRequest = field(repr=False)


@dataclass(frozen=True, slots=True)
class AlreadyConnected:
    conversation: ConversationReference


@dataclass(frozen=True, slots=True)
class AcceptedRequest:
    request: ConnectionRequest = field(repr=False)
    conversation: ConversationReference


type PreviewResult = RequestPreview | ExistingOutgoing | IncomingRequestExists | AlreadyConnected


type SendResult = SentRequest | ExistingOutgoing | IncomingRequestExists | AlreadyConnected
type RequestResult = RequestPreview | SendResult | ConnectionRequest | AcceptedRequest


@dataclass(frozen=True, slots=True)
class RequestIntent:
    fingerprint: bytes = field(repr=False)
    result: RequestResult = field(repr=False)


@dataclass(frozen=True, slots=True)
class PairState:
    relationship_id: UUID
    pair: AccountPair
    pending: ConnectionRequest | None = field(default=None, repr=False)
    conversation: ConversationReference | None = None
    sender_cooldown_until: datetime | None = None

    def __post_init__(self) -> None:
        for value in (self.pending, self.conversation):
            if value is not None and (
                value.relationship_id != self.relationship_id or value.pair != self.pair
            ):
                raise ValueError("Pair state contains another relationship")
        if self.pending is not None and not self.pending.pending:
            raise ValueError("Pending projection must use effective server time")
        if self.pending is not None and self.conversation is not None:
            raise ValueError("Connected pair cannot have an active pending request")


class RequestTransaction(DiscoveryProfileReader, Protocol):
    """Same transaction: ordered account/session locks then canonical pair/quota.

    pair_state settles due request finality using at before returning; pending and
    quota counts include pending_decline only while effective. Source readers reuse
    existing adapters on this session. No nested UoW or separate pair registry.
    """

    async def existing_pair(self, actor_id: UUID, peer_id: UUID, at: datetime) -> PairState | None:
        """Resolve canonical existing pair without creating a relationship for an unknown peer."""
        ...

    async def observe_pair(self, actor_id: UUID, peer_id: UUID, at: datetime) -> PairState | None:
        """Effective existing pair at server time; no creation or persisted settlement."""
        ...

    async def pair_state(self, actor_id: UUID, peer_id: UUID, at: datetime) -> PairState: ...

    async def quota(self, actor_id: UUID, at: datetime) -> SendQuota: ...

    async def preview(self, preview_id: UUID) -> RequestPreview | None: ...

    async def save_preview(self, preview: RequestPreview) -> None: ...

    async def request(self, request_id: UUID) -> ConnectionRequest | None: ...

    async def save_request(self, request: ConnectionRequest) -> None:
        """Persist actual revision; a new send spends daily budget in this same tx."""
        ...

    async def intent(
        self, actor_id: UUID, operation: str, key: IntentKey
    ) -> RequestIntent | None: ...

    async def remember_intent(
        self, actor_id: UUID, operation: str, key: IntentKey, intent: RequestIntent, at: datetime
    ) -> None: ...

    async def create_conversation(
        self, request: ConnectionRequest, at: datetime
    ) -> ConversationReference:
        """Real unique conversation+immutable accepted context in THIS transaction.

        No fake IDs or independent commit. SQL acceptance stays unavailable until
        main owner supplies this actual shared BE06 foundation.
        """
        ...


class RequestUnitOfWork(Protocol):
    def transaction(self, peer_id: UUID) -> AbstractAsyncContextManager[RequestTransaction]: ...


class RequestExpiryTransaction(Protocol):
    async def now(self) -> datetime: ...

    async def due_requests(self, at: datetime, limit: int) -> tuple[ConnectionRequest, ...]: ...

    async def save_request(self, request: ConnectionRequest) -> None: ...


class RequestExpiryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[RequestExpiryTransaction]: ...
