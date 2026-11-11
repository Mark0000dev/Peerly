from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.media.cleanup import TransportCleanupLease, TransportCleanupTransaction
from studymate.infrastructure.observability.media import record_media_claim
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_models import (
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.media_origins import read_media_origin
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.persistence.transport_cleanup_models import TransportCleanupRecord


@dataclass(frozen=True, slots=True)
class SqlTransportCleanupTransaction:
    session: AsyncSession

    async def now(self) -> datetime:
        return await SqlIdentityTransaction(self.session).now()

    async def claim(self, at: datetime, lease_until: datetime) -> TransportCleanupLease | None:
        record = (
            await self.session.scalars(
                select(TransportCleanupRecord)
                .join(PhotoUploadRecord, PhotoUploadRecord.id == TransportCleanupRecord.upload_id)
                .join(
                    PhotoUploadRevisionRecord,
                    (PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id)
                    & (PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version),
                )
                .where(
                    TransportCleanupRecord.cleaned_at.is_(None),
                    TransportCleanupRecord.next_attempt_at <= at,
                    or_(
                        TransportCleanupRecord.lease_until.is_(None),
                        TransportCleanupRecord.lease_until <= at,
                    ),
                    PhotoUploadRecord.upload_expires_at <= at,
                    or_(
                        PhotoUploadRevisionRecord.state.in_(
                            ("ready", "rejected", "cancelled", "expired")
                        ),
                        and_(
                            PhotoUploadRevisionRecord.state == "uploading",
                            PhotoUploadRecord.upload_expires_at <= at,
                        ),
                        PhotoUploadRecord.processing_expires_at <= at,
                    ),
                )
                .order_by(TransportCleanupRecord.next_attempt_at, TransportCleanupRecord.upload_id)
                .limit(1)
                .with_for_update(of=TransportCleanupRecord, skip_locked=True)
            )
        ).one_or_none()
        if record is None:
            return None
        record.generation, record.lease_until = uuid4(), lease_until
        record.attempts += 1
        await self.session.flush()
        upload = await self.session.get(PhotoUploadRecord, record.upload_id)
        if upload is None:
            raise RuntimeError("Cleanup source upload is unavailable")
        record_media_claim(
            record.upload_id,
            upload.account_id,
            record.generation,
            record.attempts,
            await read_media_origin(self.session, record.upload_id),
        )
        return TransportCleanupLease(record.upload_id, record.generation, record.attempts)

    async def finish(
        self, lease: TransportCleanupLease, at: datetime, retry_at: datetime | None
    ) -> bool:
        record = await self.session.get(
            TransportCleanupRecord, lease.upload_id, with_for_update=True
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
        return True


@dataclass(frozen=True, slots=True)
class SqlTransportCleanupUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[TransportCleanupTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlTransportCleanupTransaction(session)
