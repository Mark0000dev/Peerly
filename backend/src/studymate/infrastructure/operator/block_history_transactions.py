"""Account-contained actual pair and directional sources, without student/contact filters."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.block_history_ports import OperatorBlockHistoryWindow
from studymate.domain.operator.block_history import (
    OPERATOR_BLOCK_HISTORY_PAGE_SIZE,
    OperatorBlockHistoryAnchors,
    OperatorBlockHistoryHead,
)
from studymate.domain.relationships import AccountPair, BlockRevision
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.block_models import (
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction


def block_history_value(row: BlockRevisionRecord) -> BlockRevision:
    pair = AccountPair(row.low_id, row.high_id)
    if row.target_id != pair.counterpart(row.blocker_id):
        raise RuntimeError("Block history source lost its actual directional target proof")
    return BlockRevision(
        row.relationship_id, pair, row.blocker_id, row.version, row.blocked, row.changed_at
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorBlockHistoryTransaction(SqlOperatorTransaction):
    async def block_history_account(self, account_id: UUID) -> UUID | None:
        self.checked_access()
        return await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )

    async def block_history_head(
        self, account_id: UUID, relationship_id: UUID
    ) -> OperatorBlockHistoryHead | None:
        self.checked_access()
        relation = await self.session.scalar(
            select(RelationshipRecord).where(
                RelationshipRecord.id == relationship_id,
                or_(
                    RelationshipRecord.low_id == account_id,
                    RelationshipRecord.high_id == account_id,
                ),
            )
        )
        if relation is None:
            return None
        pair = AccountPair(relation.low_id, relation.high_id)
        grouped = await self.session.execute(
            select(BlockRevisionRecord.blocker_id, func.max(BlockRevisionRecord.version))
            .where(BlockRevisionRecord.relationship_id == relationship_id)
            .group_by(BlockRevisionRecord.blocker_id)
        )
        versions: dict[UUID, int] = {}
        for blocker, maximum in grouped:
            if maximum is None:
                raise RuntimeError("Block history source has no actual directional maximum")
            versions[blocker] = maximum
        current = await self.session.scalars(
            select(BlockRevisionRecord)
            .join(
                BlockRecord,
                and_(
                    BlockRecord.relationship_id == BlockRevisionRecord.relationship_id,
                    BlockRecord.blocker_id == BlockRevisionRecord.blocker_id,
                    BlockRecord.current_version == BlockRevisionRecord.version,
                ),
            )
            .where(BlockRecord.relationship_id == relationship_id)
            .order_by(BlockRevisionRecord.blocker_id.desc())
        )
        return OperatorBlockHistoryHead(
            relationship_id,
            pair,
            OperatorBlockHistoryAnchors(versions.get(pair.low, 0), versions.get(pair.high, 0)),
            tuple(block_history_value(row) for row in current),
        )

    async def block_history_revisions(
        self, head: OperatorBlockHistoryHead, window: OperatorBlockHistoryWindow
    ) -> tuple[BlockRevision, ...]:
        self.checked_access()
        source = BlockRevisionRecord
        statement = select(source).where(
            source.relationship_id == head.relationship_id,
            or_(
                and_(
                    source.blocker_id == head.pair.low, source.version <= window.anchors.low_version
                ),
                and_(
                    source.blocker_id == head.pair.high,
                    source.version <= window.anchors.high_version,
                ),
            ),
        )
        before = window.before
        if before is not None:
            statement = statement.where(
                tuple_(source.changed_at, source.blocker_id, source.version)
                < tuple_(before.changed_at, before.blocker_id, before.version)
            )
        rows = await self.session.scalars(
            statement.order_by(
                source.changed_at.desc(), source.blocker_id.desc(), source.version.desc()
            ).limit(OPERATOR_BLOCK_HISTORY_PAGE_SIZE + 1)
        )
        return tuple(block_history_value(row) for row in rows)


@dataclass(frozen=True, slots=True)
class SqlOperatorBlockHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorBlockHistoryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorBlockHistoryTransaction(session, self.recorder)
