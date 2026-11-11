from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.safety.blocks import BlockIntent, OwnBlockResult, OwnBlockSnapshot
from studymate.domain.relationships import AccountPair, BlockRevision
from studymate.domain.reports import ProfileAccessContext
from studymate.infrastructure.persistence.block_models import (
    BlockIntentRecord,
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)
from studymate.infrastructure.persistence.block_state import read_own_block
from studymate.infrastructure.persistence.discovery_exposure import record_foreground_activity
from studymate.infrastructure.persistence.identity_sessions import SqlPeerIdentityTransaction
from studymate.infrastructure.persistence.product_events import (
    record_block_event,
    record_request_outcome,
)
from studymate.infrastructure.persistence.profile_reports import SqlProfileReportTransaction
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.lifecycle import close_pair_requests


@dataclass(frozen=True, slots=True)
class SqlBlockTransaction(SqlPeerIdentityTransaction):
    async def _relationship(self, pair: AccountPair) -> RelationshipRecord | None:
        return await self.session.scalar(
            select(RelationshipRecord).where(
                RelationshipRecord.low_id == pair.low, RelationshipRecord.high_id == pair.high
            )
        )

    async def block_intent(self, actor_id: UUID, key: IntentKey) -> BlockIntent | None:
        record = await self.session.get(BlockIntentRecord, (actor_id, key.value))
        if record is None:
            return None
        result = OwnBlockResult(record.target_id, False, 0, None)
        if record.result_version:
            revision = await self.session.get(
                BlockRevisionRecord, (record.relationship_id, actor_id, record.result_version)
            )
            if revision is None:
                raise RuntimeError("Saved block revision is unavailable")
            result = OwnBlockResult(
                record.target_id, revision.blocked, revision.version, revision.changed_at
            )
        return BlockIntent(record.fingerprint, result, record.context_id)

    async def current_own_block(self, actor_id: UUID, target_id: UUID) -> OwnBlockSnapshot:
        return await read_own_block(self.session, actor_id, target_id)

    async def access_context(self, actor_id: UUID, context_id: UUID) -> ProfileAccessContext | None:
        return await SqlProfileReportTransaction(self.session).access_context(actor_id, context_id)

    async def save_block(self, revision: BlockRevision) -> None:
        relationship = await self.session.get(RelationshipRecord, revision.relationship_id)
        if relationship is None:
            self.session.add(
                RelationshipRecord(
                    id=revision.relationship_id,
                    low_id=revision.pair.low,
                    high_id=revision.pair.high,
                )
            )
            await self.session.flush()
        self.session.add(
            BlockRevisionRecord(
                relationship_id=revision.relationship_id,
                blocker_id=revision.blocker_id,
                version=revision.version,
                low_id=revision.pair.low,
                high_id=revision.pair.high,
                target_id=revision.target_id,
                blocked=revision.blocked,
                changed_at=revision.changed_at,
            )
        )
        await self.session.flush()
        current = await self.session.get(
            BlockRecord, (revision.relationship_id, revision.blocker_id)
        )
        if current is None:
            if revision.version != 1:
                raise RuntimeError("First block revision must be one")
            self.session.add(
                BlockRecord(
                    relationship_id=revision.relationship_id,
                    blocker_id=revision.blocker_id,
                    current_version=revision.version,
                )
            )
        else:
            if current.current_version != revision.version - 1:
                raise RuntimeError("Block revision must follow the saved current revision")
            current.current_version = revision.version
        await self.session.flush()
        await record_block_event(self.session, revision)
        if revision.blocked:
            await close_pair_requests(
                self.session, revision.pair, revision.blocker_id, record_request_outcome
            )

    async def remember_block_intent(
        self, actor_id: UUID, key: IntentKey, intent: BlockIntent, at: datetime
    ) -> None:
        result = intent.result
        relationship = (
            await self._relationship(AccountPair.between(actor_id, result.target_id))
            if result.version
            else None
        )
        if result.version and relationship is None:
            raise RuntimeError("Saved block relationship is unavailable")
        self.session.add(
            BlockIntentRecord(
                actor_id=actor_id,
                key=key.value,
                fingerprint=intent.fingerprint,
                target_id=result.target_id,
                relationship_id=relationship.id if relationship is not None else None,
                result_version=result.version,
                context_id=intent.context_id,
                created_at=at,
            )
        )
        await self.session.flush()
        await record_foreground_activity(self.session, actor_id, at)


@dataclass(frozen=True, slots=True)
class SqlBlockUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self, target_id: UUID) -> AsyncIterator[SqlBlockTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlBlockTransaction(session, target_id)
