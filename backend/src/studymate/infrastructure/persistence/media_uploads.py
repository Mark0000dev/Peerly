from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.media.uploads import MediaIntent, MediaTransaction, UploadBudget
from studymate.domain.media import (
    PhotoContentType,
    PhotoFailure,
    PhotoRevision,
    PhotoSource,
    PhotoUpload,
    PhotoUploadState,
)
from studymate.infrastructure.persistence.discovery_exposure import record_foreground_activity
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_models import (
    MediaIntentRecord,
    PhotoRecord,
    PhotoRevisionRecord,
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.media_origins import retain_media_origin
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.persistence.transport_cleanup_models import TransportCleanupRecord

PENDING_STATES = ("uploading", "queued", "processing")


def upload_value(root: PhotoUploadRecord, revision: PhotoUploadRevisionRecord) -> PhotoUpload:
    return PhotoUpload(
        id=root.id,
        account_id=root.account_id,
        source=PhotoSource(
            root.source_size, root.source_digest, PhotoContentType(root.content_type)
        ),
        expected_photo_version=root.expected_photo_version,
        created_at=root.created_at,
        upload_expires_at=root.upload_expires_at,
        processing_expires_at=root.processing_expires_at,
        version=revision.version,
        state=PhotoUploadState(revision.state),
        updated_at=revision.updated_at,
        attempt_id=revision.attempt_id,
        failure=PhotoFailure(revision.failure) if revision.failure is not None else None,
    )


@dataclass(frozen=True, slots=True)
class SqlMediaTransaction(SqlIdentityTransaction):
    async def current_photo(self, account_id: UUID) -> PhotoRevision | None:
        record = (
            await self.session.scalars(
                select(PhotoRevisionRecord)
                .join(
                    PhotoRecord,
                    (PhotoRecord.account_id == PhotoRevisionRecord.account_id)
                    & (PhotoRecord.current_version == PhotoRevisionRecord.version),
                )
                .where(PhotoRecord.account_id == account_id)
            )
        ).one_or_none()
        return (
            PhotoRevision(record.account_id, record.version, record.upload_id, record.saved_at)
            if record is not None
            else None
        )

    async def upload(
        self, account_id: UUID, upload_id: UUID, version: int | None = None
    ) -> PhotoUpload | None:
        statement = (
            select(PhotoUploadRecord, PhotoUploadRevisionRecord)
            .join(
                PhotoUploadRevisionRecord,
                PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id,
            )
            .where(PhotoUploadRecord.account_id == account_id, PhotoUploadRecord.id == upload_id)
        )
        statement = statement.where(
            PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version
            if version is None
            else PhotoUploadRevisionRecord.version == version
        )
        if version is None:
            statement = statement.with_for_update(
                of=PhotoUploadRecord, read=self.shared_identity_locks
            )
        row = (await self.session.execute(statement)).one_or_none()
        return upload_value(*row) if row is not None else None

    async def _pending(self, account_id: UUID) -> tuple[PhotoUpload, ...]:
        selected = (
            select(PhotoUploadRecord.id)
            .join(
                PhotoUploadRevisionRecord,
                (PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id)
                & (PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version),
            )
            .where(
                PhotoUploadRecord.account_id == account_id,
                PhotoUploadRevisionRecord.state.in_(PENDING_STATES),
            )
        )
        upload_ids = tuple(await self.session.scalars(selected))
        if not upload_ids:
            return ()
        # Actor lock prevents new foreground roots; workers may advance revisions.
        # Lock roots first, then read their current revisions in a fresh statement.
        await self.session.execute(
            select(PhotoUploadRecord.id)
            .where(PhotoUploadRecord.id.in_(upload_ids))
            .order_by(PhotoUploadRecord.id)
            .with_for_update()
        )
        records = (
            await self.session.execute(
                select(PhotoUploadRecord, PhotoUploadRevisionRecord)
                .join(
                    PhotoUploadRevisionRecord,
                    (PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id)
                    & (PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version),
                )
                .where(
                    PhotoUploadRecord.account_id == account_id,
                    PhotoUploadRecord.id.in_(upload_ids),
                    PhotoUploadRevisionRecord.state.in_(PENDING_STATES),
                )
            )
        ).all()
        return tuple(upload_value(*row) for row in records)

    async def expire_pending_uploads(self, account_id: UUID, at: datetime) -> None:
        pending = await self._pending(account_id)
        effective_at = max(at, await self.now())
        for current in pending:
            expired = current.expire(effective_at)
            if expired is not current:
                await self.save_upload(expired)

    async def upload_budget(self, account_id: UUID, since: datetime) -> UploadBudget:
        used, first = (
            await self.session.execute(
                select(func.count(), func.min(PhotoUploadRecord.created_at)).where(
                    PhotoUploadRecord.account_id == account_id, PhotoUploadRecord.created_at > since
                )
            )
        ).one()
        pending = await self._pending(account_id)
        deadline = min(
            (
                item.upload_expires_at
                if item.state == PhotoUploadState.UPLOADING
                else item.processing_expires_at
                for item in pending
            ),
            default=None,
        )
        return UploadBudget(used, first, len(pending), deadline)

    async def media_intent(self, account_id: UUID, key: IntentKey) -> MediaIntent | None:
        record = await self.session.get(MediaIntentRecord, (account_id, key.value))
        return (
            MediaIntent(record.fingerprint, record.upload_id, record.result_version)
            if record is not None
            else None
        )

    async def create_upload(self, value: PhotoUpload) -> None:
        self.session.add(
            PhotoUploadRecord(
                id=value.id,
                account_id=value.account_id,
                current_version=value.version,
                expected_photo_version=value.expected_photo_version,
                source_size=value.source.size,
                source_digest=value.source.sha256,
                content_type=value.source.content_type.value,
                created_at=value.created_at,
                upload_expires_at=value.upload_expires_at,
                processing_expires_at=value.processing_expires_at,
            )
        )
        await self.session.flush()
        await self.save_upload(value)
        self.session.add(
            TransportCleanupRecord(
                upload_id=value.id, attempts=0, next_attempt_at=value.upload_expires_at
            )
        )
        await self.session.flush()

    async def save_upload(self, value: PhotoUpload) -> None:
        await retain_media_origin(self.session, value)
        self.session.add(
            PhotoUploadRevisionRecord(
                upload_id=value.id,
                version=value.version,
                account_id=value.account_id,
                state=value.state.value,
                updated_at=value.updated_at,
                attempt_id=value.attempt_id,
                failure=value.failure.value if value.failure is not None else None,
            )
        )
        await self.session.flush()
        await self.session.execute(
            update(PhotoUploadRecord)
            .where(
                PhotoUploadRecord.id == value.id, PhotoUploadRecord.account_id == value.account_id
            )
            .values(current_version=value.version)
        )

    async def remember_media_intent(
        self, account_id: UUID, key: IntentKey, intent: MediaIntent, at: datetime
    ) -> None:
        self.session.add(
            MediaIntentRecord(
                account_id=account_id,
                key=key.value,
                fingerprint=intent.fingerprint,
                upload_id=intent.upload_id,
                result_version=intent.result_version,
                created_at=at,
            )
        )
        await self.session.flush()
        await record_foreground_activity(self.session, account_id, at)


@dataclass(frozen=True, slots=True)
class SqlMediaUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    shared_identity_locks: bool = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[MediaTransaction]:
        async with open_transaction(self.sessions, read_only=self.shared_identity_locks) as session:
            yield SqlMediaTransaction(session, shared_identity_locks=self.shared_identity_locks)
