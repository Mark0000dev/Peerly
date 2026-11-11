"""Recipient window/head are read in one SQL snapshot; the use case closes before streaming."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import Nullable, and_, false, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.domain.changes import CHANGE_PAGE_SIZE, ChangeWindow, PublishedChange
from studymate.infrastructure.changes.models import (
    ChangeHeadRecord,
    PublishedChangeRecord,
)
from studymate.infrastructure.changes.sources import project_change_hints
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.transactions import open_transaction

CHANGE_READ_DEADLINE_SECONDS = 2.0


@dataclass(slots=True)
class ChangeReadAuthority:
    recipient_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SqlChangeReadTransaction(SqlIdentityTransaction):
    authority: ChangeReadAuthority = field(default_factory=ChangeReadAuthority)

    def authenticated(self, account_id: UUID) -> None:
        SqlIdentityTransaction.authenticated(self, account_id)
        self.authority.recipient_id = account_id

    async def change_window(self, recipient_id: UUID, after: int | None) -> ChangeWindow:
        if recipient_id != self.authority.recipient_id:
            raise RuntimeError("Change journal lacks its actual authenticated recipient")
        head, journal = ChangeHeadRecord, PublishedChangeRecord
        source_filter = (
            and_(
                journal.recipient_id == head.recipient_id,
                journal.sequence > after,
                head.expired_through_sequence <= after,
                head.next_sequence > after,
            )
            if after is not None
            else false()
        )
        rows = tuple(
            await self.session.execute(
                select(
                    head,
                    Nullable(journal),
                    Nullable(ProductEventRecord),
                )
                .select_from(head)
                .outerjoin(journal, source_filter)
                .outerjoin(
                    ProductEventRecord,
                    ProductEventRecord.id == journal.canonical_event_id,
                )
                .where(head.recipient_id == recipient_id)
                .order_by(journal.sequence)
                .limit(CHANGE_PAGE_SIZE + 1)
            )
        )
        if not rows:
            return ChangeWindow(recipient_id, 0, 0, ())
        source_head = rows[0][0]
        events = tuple(event for _, _, event in rows if event is not None)
        hints = await project_change_hints(self.session, events)
        changes: list[PublishedChange] = []
        for _, row, event in rows:
            if row is None:
                if event is not None:
                    raise RuntimeError("Empty change journal row invented a canonical source")
                continue
            if event is None:
                raise RuntimeError("Published change lost its actual canonical source")
            owned = tuple(hint for hint in hints[event.id] if hint.recipient_id == recipient_id)
            if len(owned) != 1:
                raise RuntimeError("Published change lost its actual canonical recipient")
            changes.append(PublishedChange(owned[0], row.sequence, row.published_at))
        return ChangeWindow(
            recipient_id,
            source_head.next_sequence - 1,
            source_head.expired_through_sequence,
            tuple(changes),
        )


@dataclass(frozen=True, slots=True)
class SqlChangeReadUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlChangeReadTransaction]:
        try:
            async with asyncio.timeout(CHANGE_READ_DEADLINE_SECONDS):
                async with open_transaction(self.sessions) as session:
                    yield SqlChangeReadTransaction(session)
        except TimeoutError:
            raise StorageUnavailableError from None
