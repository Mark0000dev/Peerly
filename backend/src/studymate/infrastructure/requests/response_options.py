"""Scope a pending recipient before any private request or two-profile source read."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.requests.peers import request_peer
from studymate.application.requests.response_options_ports import ResponseOptionsContext
from studymate.domain.requests.projections import RequestPeerState
from studymate.infrastructure.persistence.profile_sources import (
    read_blocked_peers,
    read_profile_sources,
)
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.models import (
    ConnectionRequestRecord,
    RequestPreviewRecord,
    RequestRevisionRecord,
)
from studymate.infrastructure.requests.queries import SqlRequestQueryTransaction
from studymate.infrastructure.requests.values import request_value


@dataclass(frozen=True, slots=True)
class SqlResponseOptionsTransaction(SqlRequestQueryTransaction):
    async def response_context(
        self, actor_id: UUID, request_id: UUID
    ) -> ResponseOptionsContext | None:
        self.check_actor(actor_id)
        model = ConnectionRequestRecord
        # This guarded metadata query locks the actual incoming pending record;
        # it reads no private text, preview or academic sources for foreign callers.
        peer_id = await self.session.scalar(
            select(model.sender_id)
            .where(
                model.id == request_id,
                model.recipient_id == actor_id,
                model.state == "pending",
                model.expires_at > await self.now(),
            )
            .with_for_update(read=True, of=model)
        )
        if peer_id is None:
            return None
        sources = await read_profile_sources(self.session, (actor_id, peer_id))
        own, peer = sources.get(actor_id), sources.get(peer_id)
        blocked = peer_id in await read_blocked_peers(self.session, actor_id, (peer_id,))
        if (
            own is None
            or peer is None
            or request_peer(own, peer, blocked=blocked).state != RequestPeerState.PUBLIC
        ):
            return None
        row = (
            await self.session.execute(
                select(model, RequestRevisionRecord, RequestPreviewRecord)
                .join(
                    RequestRevisionRecord,
                    and_(
                        RequestRevisionRecord.request_id == model.id,
                        RequestRevisionRecord.version == model.current_version,
                    ),
                )
                .join(RequestPreviewRecord, RequestPreviewRecord.id == model.preview_id)
                .where(
                    model.id == request_id,
                    model.recipient_id == actor_id,
                    model.state == "pending",
                    model.expires_at > await self.now(),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return ResponseOptionsContext(request_value(*row), own, peer, blocked)


@dataclass(frozen=True, slots=True)
class SqlResponseOptionsUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlResponseOptionsTransaction]:
        async with open_transaction(self.sessions, read_only=True) as session:
            yield SqlResponseOptionsTransaction(session, shared_identity_locks=True)
