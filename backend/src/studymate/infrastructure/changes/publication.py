"""SQL-only publication; no account locks, provider calls or network waits."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.changes.publication import PUBLICATION_BATCH_SIZE
from studymate.domain.changes import MAX_DELIVERY_SEQUENCE, ChangeHint, PublishedChange
from studymate.domain.time import require_aware
from studymate.infrastructure.changes.models import (
    ChangeHeadRecord,
    ChangeOutboxRecord,
    PublishedChangeRecord,
)
from studymate.infrastructure.changes.sources import project_change_hints
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(slots=True)
class PublicationAuthority:
    records: tuple[ChangeOutboxRecord, ...] = ()
    hints: tuple[ChangeHint, ...] = ()
    claimed: bool = False
    published: bool = False


@dataclass(frozen=True, slots=True)
class SqlChangePublicationTransaction:
    session: AsyncSession
    authority: PublicationAuthority = field(default_factory=PublicationAuthority)

    async def now(self) -> datetime:
        return await SqlIdentityTransaction(self.session).now()

    async def claim_changes(self, limit: int) -> tuple[ChangeHint, ...]:
        if self.authority.claimed or not 1 <= limit <= PUBLICATION_BATCH_SIZE:
            raise RuntimeError("Publication requires one bounded claim per transaction")
        rows = tuple(
            await self.session.execute(
                select(ChangeOutboxRecord, ProductEventRecord)
                .join(
                    ProductEventRecord,
                    ProductEventRecord.id == ChangeOutboxRecord.canonical_event_id,
                )
                .where(ChangeOutboxRecord.published_sequence.is_(None))
                .order_by(
                    ChangeOutboxRecord.staged_at,
                    ChangeOutboxRecord.canonical_event_id,
                    ChangeOutboxRecord.recipient_id,
                )
                .limit(limit)
                .with_for_update(skip_locked=True, of=ChangeOutboxRecord)
            )
        )
        sources = {event.id: event for _, event in rows}
        projected = await project_change_hints(self.session, tuple(sources.values()))
        hints: list[ChangeHint] = []
        for record, event in rows:
            owned = tuple(
                hint for hint in projected[event.id] if hint.recipient_id == record.recipient_id
            )
            if len(owned) != 1:
                raise RuntimeError("Queued invalidation lacks its actual canonical recipient")
            hints.append(owned[0])
        self.authority.records = tuple(record for record, _ in rows)
        self.authority.hints = tuple(hints)
        self.authority.claimed = True
        return self.authority.hints

    async def publish_changes(
        self, changes: tuple[ChangeHint, ...], at: datetime
    ) -> tuple[PublishedChange, ...]:
        require_aware(at)
        if (
            not self.authority.claimed
            or self.authority.published
            or changes != self.authority.hints
        ):
            raise RuntimeError("Publication differs from its actual locked claim")
        recipients = tuple(sorted({hint.recipient_id for hint in changes}))
        if not recipients:
            raise RuntimeError("Empty source cannot spend a recipient sequence")
        await self.session.execute(
            insert(ChangeHeadRecord)
            .values(
                [
                    {"recipient_id": recipient, "next_sequence": 1, "expired_through_sequence": 0}
                    for recipient in recipients
                ]
            )
            .on_conflict_do_nothing(index_elements=[ChangeHeadRecord.recipient_id])
        )
        heads = {
            head.recipient_id: head
            for head in await self.session.scalars(
                select(ChangeHeadRecord)
                .where(ChangeHeadRecord.recipient_id.in_(recipients))
                .order_by(ChangeHeadRecord.recipient_id)
                .with_for_update()
            )
        }
        if set(heads) != set(recipients):
            raise RuntimeError("Publication lost an actual recipient head")
        published: list[PublishedChange] = []
        for record, hint in zip(self.authority.records, changes, strict=True):
            head = heads[hint.recipient_id]
            sequence = head.next_sequence
            if sequence >= MAX_DELIVERY_SEQUENCE:
                raise RuntimeError("Recipient delivery sequence is exhausted")
            published.append(PublishedChange(hint, sequence, at))
            self.session.add(
                PublishedChangeRecord(
                    recipient_id=hint.recipient_id,
                    sequence=sequence,
                    canonical_event_id=hint.canonical_event_id,
                    published_at=at,
                )
            )
            head.next_sequence += 1
            record.published_sequence = sequence
            record.published_at = at
        await self.session.flush()
        self.authority.published = True
        return tuple(published)


@dataclass(frozen=True, slots=True)
class SqlChangePublicationUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlChangePublicationTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlChangePublicationTransaction(session)
