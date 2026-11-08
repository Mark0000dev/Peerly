"""Bounded prefix pruning under publisher-compatible heads, without canonical deletion."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.changes.retention import (
    RETENTION_PREFIX_LIMIT,
    RETENTION_RECIPIENT_BATCH,
)
from studymate.domain.time import require_aware
from studymate.infrastructure.changes.models import (
    ChangeHeadRecord,
    PublishedChangeRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction

if TYPE_CHECKING:
    from uuid import UUID


@dataclass(frozen=True, slots=True)
class SqlChangeRetentionTransaction:
    session: AsyncSession

    async def now(self) -> datetime:
        return await SqlIdentityTransaction(self.session).now()

    async def prune_changes(self, before: datetime, recipients: int, per_recipient: int) -> int:
        require_aware(before)
        if (
            not 1 <= recipients <= RETENTION_RECIPIENT_BATCH
            or not 1 <= per_recipient <= RETENTION_PREFIX_LIMIT
        ):
            raise ValueError("Transport retention requires bounded recipient prefixes")
        head, journal = ChangeHeadRecord, PublishedChangeRecord
        old_prefix = (
            select(journal.sequence)
            .where(
                journal.recipient_id == head.recipient_id,
                journal.sequence == head.expired_through_sequence + 1,
                journal.published_at < before,
            )
            .correlate(head)
            .exists()
        )
        heads = tuple(
            await self.session.scalars(
                select(head)
                .where(old_prefix)
                .order_by(head.recipient_id)
                .limit(recipients)
                .with_for_update(skip_locked=True)
            )
        )
        if not heads:
            return 0
        ranges = tuple(
            and_(
                journal.recipient_id == row.recipient_id,
                journal.sequence > row.expired_through_sequence,
                journal.sequence <= row.expired_through_sequence + per_recipient,
            )
            for row in heads
        )
        rows = tuple(
            await self.session.scalars(
                select(journal).where(or_(*ranges)).order_by(journal.recipient_id, journal.sequence)
            )
        )
        by_recipient: dict[UUID, list[PublishedChangeRecord]] = {
            item.recipient_id: [] for item in heads
        }
        for row in rows:
            by_recipient[row.recipient_id].append(row)
        cutoffs = []
        expected = 0
        for recipient_head in heads:
            floor = recipient_head.expired_through_sequence
            for change in by_recipient[recipient_head.recipient_id]:
                if change.sequence != floor + 1:
                    raise RuntimeError("Transport pruning encountered a noncontiguous source")
                if change.published_at >= before:
                    break
                floor = change.sequence
            if floor > recipient_head.expired_through_sequence:
                expected += floor - recipient_head.expired_through_sequence
                cutoffs.append(
                    and_(
                        journal.recipient_id == recipient_head.recipient_id,
                        journal.sequence <= floor,
                    )
                )
                recipient_head.expired_through_sequence = floor
        if not cutoffs:
            return 0
        deleted = tuple(
            await self.session.execute(
                delete(journal)
                .where(or_(*cutoffs))
                .returning(journal.recipient_id, journal.sequence)
            )
        )
        if len(deleted) != expected:
            raise RuntimeError("Transport expiry floor differs from its actual removed prefix")
        await self.session.flush()
        return len(deleted)


@dataclass(frozen=True, slots=True)
class SqlChangeRetentionUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlChangeRetentionTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlChangeRetentionTransaction(session)
