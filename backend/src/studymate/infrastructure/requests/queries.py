from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.requests.peers import request_peer
from studymate.application.requests.query_ports import (
    REQUEST_PAGE_SIZE,
    RequestListQuery,
    RequestReadRow,
)
from studymate.domain.requests.limits import SendQuota, send_day
from studymate.domain.requests.projections import (
    RequestBox,
    RequestListView,
    RequestPeerState,
    RequestVisibility,
)
from studymate.domain.requests.states import RequestUnavailableError
from studymate.domain.requests.views import RequestDisclosure
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.profile_sources import (
    read_blocked_peers,
    read_profile_sources,
)
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestPreviewRecord,
    RequestRevisionRecord,
    RequestSendDayRecord,
)
from studymate.infrastructure.requests.transactions import RequestAuthority
from studymate.infrastructure.requests.values import request_value
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)


@dataclass(frozen=True, slots=True)
class SqlRequestQueryTransaction(SqlIdentityTransaction):
    authority: RequestAuthority = field(default_factory=RequestAuthority)

    def authenticated(self, account_id: UUID) -> None:
        SqlIdentityTransaction.authenticated(self, account_id)
        self.authority.actor_id = account_id

    def check_actor(self, account_id: UUID) -> None:
        if self.authority.actor_id != account_id:
            raise RuntimeError("Request read differs from authenticated actor")

    async def list_requests(self, query: RequestListQuery) -> tuple[RequestReadRow, ...]:
        self.check_actor(query.actor_id)
        request = ConnectionRequestRecord
        revision = RequestRevisionRecord
        now = await self.now()
        pending = and_(
            request.state.in_(("pending", "pending_decline")),
            request.expires_at > now,
            or_(request.state == "pending", revision.decline_until > now),
        )
        active = or_(pending, request.state == "accepted")
        state_filter = active if query.view == RequestListView.ACTIVE else ~active
        if query.view == RequestListView.RECENTLY_DECLINED:
            state_filter = and_(pending, request.state == "pending_decline")
        direction = request.recipient_id if query.box == RequestBox.RECEIVED else request.sender_id
        statement = (
            select(request.id)
            .join(
                revision,
                and_(
                    revision.request_id == request.id, revision.version == request.current_version
                ),
            )
            .where(direction == query.actor_id, request.sent_at <= query.as_of, state_filter)
        )
        if query.cursor is not None:
            statement = statement.where(
                tuple_(request.sent_at, request.id)
                < tuple_(query.cursor.sent_at, query.cursor.request_id)
            )
        ids = tuple(
            await self.session.scalars(
                statement.order_by(request.sent_at.desc(), request.id.desc()).limit(
                    REQUEST_PAGE_SIZE + 1
                )
            )
        )
        return await self.read_rows(query.actor_id, ids)

    async def owned_request(self, actor_id: UUID, request_id: UUID) -> RequestReadRow | None:
        self.check_actor(actor_id)
        rows = await self.read_rows(actor_id, (request_id,))
        return rows[0] if rows else None

    async def read_rows(self, actor_id: UUID, ids: tuple[UUID, ...]) -> tuple[RequestReadRow, ...]:
        self.check_actor(actor_id)
        if not ids:
            return ()
        request = ConnectionRequestRecord
        acknowledged = (
            select(RequestViewAcknowledgementRecord.id)
            .where(
                RequestViewAcknowledgementRecord.viewer_id == actor_id,
                RequestViewAcknowledgementRecord.request_id == request.id,
            )
            .exists()
        )
        rows = (
            await self.session.execute(
                select(request, RequestRevisionRecord, RequestPreviewRecord, acknowledged)
                .join(
                    RequestRevisionRecord,
                    and_(
                        RequestRevisionRecord.request_id == request.id,
                        RequestRevisionRecord.version == request.current_version,
                    ),
                )
                .join(RequestPreviewRecord, RequestPreviewRecord.id == request.preview_id)
                .where(
                    request.id.in_(ids),
                    or_(request.sender_id == actor_id, request.recipient_id == actor_id),
                )
                .order_by(request.sent_at.desc(), request.id.desc())
            )
        ).all()
        peers = tuple(
            dict.fromkeys(
                row.recipient_id if row.sender_id == actor_id else row.sender_id
                for row, _, _, _ in rows
            )
        )
        sources = await read_profile_sources(self.session, (actor_id, *peers))
        blocked = await read_blocked_peers(self.session, actor_id, peers)
        result: list[RequestReadRow] = []
        for record, revision, preview, has_ack in rows:
            peer_id = record.recipient_id if record.sender_id == actor_id else record.sender_id
            peer = request_peer(
                sources.get(actor_id), sources.get(peer_id), blocked=peer_id in blocked
            )
            allowed = peer.state == RequestPeerState.PUBLIC
            result.append(
                RequestReadRow(
                    request_value(record, revision, preview),
                    RequestVisibility(bool(has_ack), allowed, allowed),
                    peer,
                )
            )
        return tuple(result)

    async def quota(self, actor_id: UUID, at: datetime) -> SendQuota:
        self.check_actor(actor_id)
        request, revision = ConnectionRequestRecord, RequestRevisionRecord
        outgoing = await self.session.scalar(
            select(func.count())
            .select_from(request)
            .join(
                revision,
                and_(
                    revision.request_id == request.id, revision.version == request.current_version
                ),
            )
            .where(
                request.sender_id == actor_id,
                request.state.in_(("pending", "pending_decline")),
                request.expires_at > at,
                or_(request.state == "pending", revision.decline_until > at),
            )
        )
        daily = await self.session.get(RequestSendDayRecord, (actor_id, send_day(at)))
        return SendQuota(outgoing or 0, daily.successful_count if daily is not None else 0)

    async def unread_received(self, actor_id: UUID, at: datetime) -> int:
        self.check_actor(actor_id)
        request = ConnectionRequestRecord
        acknowledged = (
            select(RequestViewAcknowledgementRecord.id)
            .where(
                RequestViewAcknowledgementRecord.viewer_id == actor_id,
                RequestViewAcknowledgementRecord.request_id == request.id,
            )
            .exists()
        )
        count = await self.session.scalar(
            select(func.count())
            .select_from(request)
            .where(
                request.recipient_id == actor_id,
                request.state == "pending",
                request.expires_at > at,
                ~acknowledged,
            )
        )
        return count or 0

    async def disclose(self, source: RequestDisclosure) -> None:
        self.check_actor(source.viewer_id)
        record = await self.session.scalar(
            select(ConnectionRequestRecord).where(
                ConnectionRequestRecord.id == source.request_id,
                or_(
                    ConnectionRequestRecord.sender_id == source.viewer_id,
                    ConnectionRequestRecord.recipient_id == source.viewer_id,
                ),
            )
        )
        if record is None:
            raise RequestUnavailableError
        origin = current_origin()
        self.session.add(
            RequestDisclosureRecord(
                id=source.id,
                viewer_id=source.viewer_id,
                request_id=source.request_id,
                stored_version=source.stored_version,
                sender_id=record.sender_id,
                recipient_id=record.recipient_id,
                created_at=source.created_at,
                http_request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlRequestQueryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    shared_identity_locks: bool = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlRequestQueryTransaction]:
        async with open_transaction(self.sessions, read_only=self.shared_identity_locks) as session:
            yield SqlRequestQueryTransaction(
                session, shared_identity_locks=self.shared_identity_locks
            )
