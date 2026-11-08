from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.domain.requests.states import ConnectionRequest
from studymate.infrastructure.persistence.block_models import RelationshipRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.events import RequestOutcomeRecorder
from studymate.infrastructure.requests.models import ConnectionRequestRecord, RequestRevisionRecord
from studymate.infrastructure.requests.reads import read_request
from studymate.infrastructure.requests.writes import save_request


@dataclass(frozen=True, slots=True)
class SqlRequestExpiryTransaction:
    session: AsyncSession
    recorder: RequestOutcomeRecorder

    async def now(self) -> datetime:
        return await SqlIdentityTransaction(self.session).now()

    async def due_requests(self, at: datetime, limit: int) -> tuple[ConnectionRequest, ...]:
        statement = (
            select(ConnectionRequestRecord)
            .join(
                RequestRevisionRecord,
                (RequestRevisionRecord.request_id == ConnectionRequestRecord.id)
                & (RequestRevisionRecord.version == ConnectionRequestRecord.current_version),
            )
            .where(
                ConnectionRequestRecord.state.in_(("pending", "pending_decline")),
                or_(
                    ConnectionRequestRecord.expires_at <= at,
                    and_(
                        ConnectionRequestRecord.state == "pending_decline",
                        RequestRevisionRecord.decline_until <= at,
                    ),
                ),
            )
            .order_by(ConnectionRequestRecord.expires_at, ConnectionRequestRecord.id)
            .limit(limit)
        )
        candidates = tuple(await self.session.scalars(statement))
        # Every account in the bounded batch is locked globally sorted BEFORE any
        # relationship. Sequential pair locks could reverse order across a batch.
        accounts = sorted(
            {account for request in candidates for account in (request.low_id, request.high_id)}
        )
        if not accounts:
            return ()
        await self.session.execute(
            select(AccountRecord.id)
            .where(AccountRecord.id.in_(accounts))
            .order_by(AccountRecord.id)
            .with_for_update(key_share=True)
        )
        relationships = sorted({request.relationship_id for request in candidates})
        await self.session.execute(
            select(RelationshipRecord.id)
            .where(RelationshipRecord.id.in_(relationships))
            .order_by(RelationshipRecord.id)
            .with_for_update()
        )
        requests = []
        for candidate in candidates:
            await self.session.execute(
                select(ConnectionRequestRecord.id)
                .where(ConnectionRequestRecord.id == candidate.id)
                .with_for_update()
            )
            current = await read_request(self.session, candidate.id)
            if (
                current is not None
                and current.pending
                and current.changed_at <= at
                and current.effective(at) != current
            ):
                requests.append(current)
        return tuple(requests)

    async def save_request(self, request: ConnectionRequest) -> None:
        await save_request(self.session, request, None, self.recorder)


@dataclass(frozen=True, slots=True)
class SqlRequestExpiryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: RequestOutcomeRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlRequestExpiryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlRequestExpiryTransaction(session, self.recorder)
