from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.safety.block_list import BLOCKS_PAGE_SIZE, BlockCursor, OwnBlockedPerson
from studymate.application.safety.blocks import OwnBlockResult
from studymate.domain.profiles import DisplayName
from studymate.infrastructure.persistence.block_models import (
    BlockIntentRecord,
    BlockRecord,
    BlockRevisionRecord,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.profile_models import ProfileRevisionRecord
from studymate.infrastructure.persistence.report_models import ProfileAccessRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOwnBlocksTransaction(SqlIdentityTransaction):
    async def blocked_people(
        self, actor_id: UUID, after: BlockCursor | None, limit: int
    ) -> tuple[OwnBlockedPerson, ...]:
        if not 1 <= limit <= BLOCKS_PAGE_SIZE + 1:
            raise ValueError("Own block projection limit exceeds its safety bound")
        disclosure = (
            select(BlockIntentRecord.context_id)
            .where(
                BlockIntentRecord.actor_id == actor_id,
                BlockIntentRecord.target_id == BlockRevisionRecord.target_id,
                BlockIntentRecord.context_id.is_not(None),
            )
            .order_by(BlockIntentRecord.created_at.desc(), BlockIntentRecord.key.desc())
            .limit(1)
            .correlate(BlockRevisionRecord)
            .scalar_subquery()
        )
        statement = (
            select(
                BlockRevisionRecord, ProfileRevisionRecord.display_name, AccountRecord.deleted_at
            )
            .join(
                BlockRecord,
                (BlockRecord.relationship_id == BlockRevisionRecord.relationship_id)
                & (BlockRecord.blocker_id == BlockRevisionRecord.blocker_id)
                & (BlockRecord.current_version == BlockRevisionRecord.version),
            )
            .join(AccountRecord, AccountRecord.id == BlockRevisionRecord.target_id)
            .outerjoin(
                ProfileAccessRecord,
                (ProfileAccessRecord.id == disclosure)
                & (ProfileAccessRecord.viewer_id == actor_id)
                & (ProfileAccessRecord.target_id == BlockRevisionRecord.target_id),
            )
            .outerjoin(
                ProfileRevisionRecord,
                (ProfileRevisionRecord.account_id == ProfileAccessRecord.target_id)
                & (ProfileRevisionRecord.version == ProfileAccessRecord.profile_version),
            )
            .where(
                BlockRevisionRecord.blocker_id == actor_id, BlockRevisionRecord.blocked.is_(True)
            )
        )
        if after is not None:
            statement = statement.where(
                or_(
                    BlockRevisionRecord.changed_at < after.changed_at,
                    and_(
                        BlockRevisionRecord.changed_at == after.changed_at,
                        BlockRevisionRecord.target_id > after.target_id,
                    ),
                )
            )
        rows = (
            await self.session.execute(
                statement.order_by(
                    BlockRevisionRecord.changed_at.desc(), BlockRevisionRecord.target_id
                ).limit(limit)
            )
        ).all()
        return tuple(
            OwnBlockedPerson(
                record.blocker_id,
                OwnBlockResult(record.target_id, record.blocked, record.version, record.changed_at),
                DisplayName(name) if name is not None else None,
                deleted_at is not None,
            )
            for record, name, deleted_at in rows
        )


@dataclass(frozen=True, slots=True)
class SqlOwnBlocksUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOwnBlocksTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOwnBlocksTransaction(session)
