from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, case, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.requests.ports import (
    ConversationReference,
    PairState,
    RequestIntent,
    RequestPreview,
)
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.limits import SendQuota, send_day
from studymate.domain.requests.states import (
    DECLINE_COOLDOWN,
    WITHDRAW_COOLDOWN,
    ConnectionRequest,
    RequestUnavailableError,
)
from studymate.infrastructure.persistence.block_models import RelationshipRecord
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.conversations import (
    conversation_reference,
    create_request_conversation,
)
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileTransaction
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.events import RequestOutcomeRecorder
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestCommandIntentRecord,
    RequestPreviewRecord,
    RequestRevisionRecord,
    RequestSendDayRecord,
)
from studymate.infrastructure.requests.reads import intent_result, read_preview, read_request
from studymate.infrastructure.requests.values import preview_record
from studymate.infrastructure.requests.writes import IntentWrite, save_request, write_intent


@dataclass(slots=True)
class RequestAuthority:
    actor_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SqlRequestTransaction(SqlDiscoveryProfileTransaction):
    recorder: RequestOutcomeRecorder
    authority: RequestAuthority = field(default_factory=RequestAuthority)

    def authenticated(self, account_id: UUID) -> None:
        SqlIdentityTransaction.authenticated(self, account_id)
        self.authority.actor_id = account_id

    def actor_id(self) -> UUID:
        if self.authority.actor_id is None:
            raise RuntimeError("Request transaction lacks actual authenticated actor")
        return self.authority.actor_id

    def pair(self) -> AccountPair:
        if self.actor_id() == self.peer_id:
            raise RequestUnavailableError
        return AccountPair.between(self.actor_id(), self.peer_id)

    async def intent(self, actor_id: UUID, operation: str, key: IntentKey) -> RequestIntent | None:
        self.check_actor(actor_id)
        record = await self.session.get(
            RequestCommandIntentRecord, (actor_id, operation, key.value)
        )
        return (
            RequestIntent(record.fingerprint, await intent_result(self.session, record))
            if record is not None
            else None
        )

    async def remember_intent(
        self, actor_id: UUID, operation: str, key: IntentKey, intent: RequestIntent, at: datetime
    ) -> None:
        self.check_actor(actor_id)
        await write_intent(
            self.session, IntentWrite(actor_id, self.peer_id, operation, key, intent, at)
        )

    def check_actor(self, actor_id: UUID) -> None:
        if actor_id != self.actor_id():
            raise RuntimeError("Request actor differs from authenticated identity")

    async def preview(self, preview_id: UUID) -> RequestPreview | None:
        record = await self.session.scalar(
            select(RequestPreviewRecord.id).where(
                RequestPreviewRecord.id == preview_id,
                RequestPreviewRecord.sender_id == self.actor_id(),
                RequestPreviewRecord.recipient_id == self.peer_id,
            )
        )
        return await read_preview(self.session, record) if record is not None else None

    async def save_preview(self, preview: RequestPreview) -> None:
        if (preview.context.sender_id, preview.context.recipient_id) != (
            self.actor_id(),
            self.peer_id,
        ):
            raise RuntimeError("Cannot save another actors preview")
        self.session.add(preview_record(preview))
        await self.session.flush()

    async def relationship(self, pair: AccountPair) -> RelationshipRecord:
        await self.session.execute(
            insert(RelationshipRecord)
            .values(id=uuid4(), low_id=pair.low, high_id=pair.high)
            .on_conflict_do_nothing(index_elements=["low_id", "high_id"])
        )
        return (
            await self.session.scalars(
                select(RelationshipRecord)
                .where(
                    RelationshipRecord.low_id == pair.low, RelationshipRecord.high_id == pair.high
                )
                .with_for_update()
            )
        ).one()

    async def existing_pair(self, actor_id: UUID, peer_id: UUID, at: datetime) -> PairState | None:
        self.check_actor(actor_id)
        if peer_id != self.peer_id:
            raise RuntimeError("Request peer differs from transaction scope")
        pair = self.pair()
        known = await self.session.scalar(
            select(RelationshipRecord.id).where(
                RelationshipRecord.low_id == pair.low, RelationshipRecord.high_id == pair.high
            )
        )
        return await self.pair_state(actor_id, peer_id, at) if known is not None else None

    async def observe_pair(self, actor_id: UUID, peer_id: UUID, at: datetime) -> PairState | None:
        self.check_actor(actor_id)
        if peer_id != self.peer_id:
            raise RuntimeError("Request peer differs from transaction scope")
        pair = self.pair()
        relationship = await self.session.scalar(
            select(RelationshipRecord).where(
                RelationshipRecord.low_id == pair.low, RelationshipRecord.high_id == pair.high
            )
        )
        return (
            await self.read_pair(relationship, actor_id, at, settle_due=False)
            if relationship is not None
            else None
        )

    async def pair_state(self, actor_id: UUID, peer_id: UUID, at: datetime) -> PairState:
        self.check_actor(actor_id)
        if peer_id != self.peer_id:
            raise RuntimeError("Request peer differs from transaction scope")
        pair = self.pair()
        relationship = await self.relationship(pair)
        return await self.read_pair(relationship, actor_id, at, settle_due=True)

    async def read_pair(
        self, relationship: RelationshipRecord, actor_id: UUID, at: datetime, *, settle_due: bool
    ) -> PairState:
        pair = self.pair()
        pending_id = await self.session.scalar(
            select(ConnectionRequestRecord.id)
            .where(
                ConnectionRequestRecord.relationship_id == relationship.id,
                ConnectionRequestRecord.state.in_(("pending", "pending_decline")),
            )
            .with_for_update()
        )
        pending = await read_request(self.session, pending_id) if pending_id is not None else None
        effective_cooldown = None
        if pending is not None:
            effective = pending.effective(at)
            if effective.context.sender_id == actor_id:
                effective_cooldown = effective.sender_cooldown_until
            if settle_due and effective != pending:
                await save_request(self.session, effective, None, self.recorder)
            pending = effective if effective.pending else None
        conversation = await self.session.scalar(
            select(ConversationRecord).where(ConversationRecord.relationship_id == relationship.id)
        )
        cooldown = await self.session.scalar(
            select(
                cast(
                    func.max(
                        case(
                            (
                                RequestRevisionRecord.state == "declined",
                                RequestRevisionRecord.changed_at + DECLINE_COOLDOWN,
                            ),
                            else_=RequestRevisionRecord.changed_at + WITHDRAW_COOLDOWN,
                        )
                    ),
                    DateTime(timezone=True),
                )
            )
            .select_from(ConnectionRequestRecord)
            .join(
                RequestRevisionRecord,
                (RequestRevisionRecord.request_id == ConnectionRequestRecord.id)
                & (RequestRevisionRecord.version == ConnectionRequestRecord.current_version),
            )
            .where(
                ConnectionRequestRecord.relationship_id == relationship.id,
                ConnectionRequestRecord.sender_id == actor_id,
                RequestRevisionRecord.state.in_(("declined", "withdrawn")),
            )
        )
        if effective_cooldown is not None:
            cooldown = (
                max(cooldown, effective_cooldown) if cooldown is not None else effective_cooldown
            )
        return PairState(
            relationship.id,
            pair,
            pending,
            conversation_reference(conversation) if conversation is not None else None,
            cooldown,
        )

    async def quota(self, actor_id: UUID, at: datetime) -> SendQuota:
        self.check_actor(actor_id)
        pending = (
            await self.session.scalars(
                select(func.count())
                .select_from(ConnectionRequestRecord)
                .join(
                    RequestRevisionRecord,
                    (RequestRevisionRecord.request_id == ConnectionRequestRecord.id)
                    & (RequestRevisionRecord.version == ConnectionRequestRecord.current_version),
                )
                .where(
                    ConnectionRequestRecord.sender_id == actor_id,
                    ConnectionRequestRecord.state.in_(("pending", "pending_decline")),
                    ConnectionRequestRecord.expires_at > at,
                    or_(
                        ConnectionRequestRecord.state == "pending",
                        RequestRevisionRecord.decline_until > at,
                    ),
                )
            )
        ).one()
        counter = await self.session.get(RequestSendDayRecord, (actor_id, send_day(at)))
        return SendQuota(pending, counter.successful_count if counter is not None else 0)

    async def request(self, request_id: UUID) -> ConnectionRequest | None:
        pair = self.pair()
        relationship_id = await self.session.scalar(
            select(ConnectionRequestRecord.relationship_id).where(
                ConnectionRequestRecord.id == request_id,
                ConnectionRequestRecord.low_id == pair.low,
                ConnectionRequestRecord.high_id == pair.high,
            )
        )
        if relationship_id is None:
            return None
        await self.session.execute(
            select(RelationshipRecord.id)
            .where(RelationshipRecord.id == relationship_id)
            .with_for_update()
        )
        await self.session.execute(
            select(ConnectionRequestRecord.id)
            .where(ConnectionRequestRecord.id == request_id)
            .with_for_update()
        )
        return await read_request(self.session, request_id)

    async def save_request(self, request: ConnectionRequest) -> None:
        if request.pair != self.pair():
            raise RuntimeError("Cannot save another request pair")
        await save_request(self.session, request, self.actor_id(), self.recorder)

    async def create_conversation(
        self, request: ConnectionRequest, at: datetime
    ) -> ConversationReference:
        if request.pair != self.pair() or request.context.recipient_id != self.actor_id():
            raise RequestUnavailableError
        return await create_request_conversation(self.session, request, at)


@dataclass(frozen=True, slots=True)
class SqlRequestUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: RequestOutcomeRecorder

    @asynccontextmanager
    async def transaction(self, peer_id: UUID) -> AsyncIterator[SqlRequestTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlRequestTransaction(session, peer_id, self.recorder)
