from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.safety.blocks import OwnBlockSnapshot
from studymate.domain.relationships import AccountPair, BlockRevision
from studymate.infrastructure.persistence.block_models import (
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)


async def read_own_block(
    session: AsyncSession, actor_id: UUID, target_id: UUID
) -> OwnBlockSnapshot:
    pair = AccountPair.between(actor_id, target_id)
    relationship = await session.scalar(
        select(RelationshipRecord).where(
            RelationshipRecord.low_id == pair.low, RelationshipRecord.high_id == pair.high
        )
    )
    if relationship is None:
        return OwnBlockSnapshot(pair, None, None)
    current = await session.get(BlockRecord, (relationship.id, actor_id))
    if current is None:
        return OwnBlockSnapshot(pair, relationship.id, None)
    revision = await session.get(
        BlockRevisionRecord, (relationship.id, actor_id, current.current_version)
    )
    if revision is None:
        raise RuntimeError("Current block revision is unavailable")
    value = BlockRevision(
        revision.relationship_id,
        AccountPair(revision.low_id, revision.high_id),
        revision.blocker_id,
        revision.version,
        revision.blocked,
        revision.changed_at,
    )
    return OwnBlockSnapshot(pair, relationship.id, value)
