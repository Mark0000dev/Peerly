"""Lease-fenced transport-only cleanup against actual image state and fixed deadlines."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.media.cleanup import TransportCleanupLease
from studymate.infrastructure.chat_images.cleanup_models import ChatImageTransportCleanupRecord
from studymate.infrastructure.chat_images.models import ChatImageRecord, ChatImageRevisionRecord
from studymate.infrastructure.chat_images.origins import read_image_queue_origin
from studymate.infrastructure.observability.media import record_media_claim
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlImageCleanupTransaction:
    session: AsyncSession

    async def now(self) -> datetime:
        return await SqlIdentityTransaction(self.session).now()

    async def claim(self, at: datetime, lease_until: datetime) -> TransportCleanupLease | None:
        root, revision, cleanup = (
            ChatImageRecord,
            ChatImageRevisionRecord,
            ChatImageTransportCleanupRecord,
        )
        row = (
            await self.session.execute(
                select(cleanup, root.account_id)
                .join(root, root.id == cleanup.image_id)
                .join(
                    revision,
                    and_(revision.image_id == root.id, revision.version == root.current_version),
                )
                .where(
                    cleanup.cleaned_at.is_(None),
                    cleanup.next_attempt_at <= at,
                    or_(cleanup.lease_until.is_(None), cleanup.lease_until <= at),
                    root.upload_expires_at <= at,
                    or_(
                        revision.state.in_(("ready", "rejected", "cancelled", "expired")),
                        and_(revision.state == "uploading", root.upload_expires_at <= at),
                        root.processing_expires_at <= at,
                    ),
                )
                .order_by(cleanup.next_attempt_at, cleanup.image_id)
                .limit(1)
                .with_for_update(of=cleanup, skip_locked=True)
            )
        ).one_or_none()
        if row is None:
            return None
        record, account_id = row
        record.generation, record.lease_until = uuid4(), lease_until
        record.attempts += 1
        await self.session.flush()
        record_media_claim(
            record.image_id,
            account_id,
            record.generation,
            record.attempts,
            await read_image_queue_origin(self.session, record.image_id),
        )
        return TransportCleanupLease(record.image_id, record.generation, record.attempts)

    async def finish(
        self, lease: TransportCleanupLease, at: datetime, retry_at: datetime | None
    ) -> bool:
        record = await self.session.get(
            ChatImageTransportCleanupRecord, lease.upload_id, with_for_update=True
        )
        at = max(at, await self.now())
        if (
            record is None
            or record.generation != lease.generation
            or record.cleaned_at is not None
            or record.lease_until is None
            or record.lease_until <= at
        ):
            return False
        record.generation, record.lease_until = None, None
        if retry_at is None:
            record.cleaned_at = at
        else:
            record.next_attempt_at = max(at, retry_at)
        await self.session.flush()
        return True


@dataclass(frozen=True, slots=True)
class SqlImageCleanupUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlImageCleanupTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlImageCleanupTransaction(session)
