from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.media.worker import (
    MAX_PHOTO_ATTEMPTS,
    PhotoImageInfo,
    PhotoLease,
    PhotoProcessingStep,
    PhotoWorkerTransaction,
)
from studymate.domain.media import PhotoFailure, PhotoRevision, PhotoUpload, PhotoUploadState
from studymate.infrastructure.observability.media import record_media_claim
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_models import (
    PhotoRecord,
    PhotoRevisionRecord,
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.media_origins import read_media_origin
from studymate.infrastructure.persistence.media_uploads import SqlMediaTransaction, upload_value
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from studymate.infrastructure.persistence.product_events import record_photo_published
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlPhotoWorkerTransaction:
    session: AsyncSession

    async def now(self) -> datetime:
        return await SqlIdentityTransaction(self.session).now()

    async def expire_uploads(self, at: datetime, batch: int) -> None:
        rows = (
            await self.session.execute(
                select(PhotoUploadRecord, PhotoUploadRevisionRecord)
                .join(
                    PhotoUploadRevisionRecord,
                    (PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id)
                    & (PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version),
                )
                .where(
                    or_(
                        and_(
                            PhotoUploadRevisionRecord.state == "uploading",
                            PhotoUploadRecord.upload_expires_at <= at,
                        ),
                        and_(
                            PhotoUploadRevisionRecord.state.in_(("queued", "processing")),
                            PhotoUploadRecord.processing_expires_at <= at,
                        ),
                    )
                )
                .order_by(PhotoUploadRecord.id)
                .limit(batch)
                .with_for_update(of=PhotoUploadRecord, skip_locked=True)
            )
        ).all()
        for root, revision in rows:
            value = upload_value(root, revision)
            await SqlMediaTransaction(self.session).save_upload(value.expire(at))
            if value.attempt_id is not None:
                attempt = await self.session.get(
                    PhotoAttemptRecord, value.attempt_id, with_for_update=True
                )
                if attempt is not None:
                    _finish(attempt, "stale", at)

    async def claim(self, at: datetime, lease_until: datetime) -> PhotoLease | None:
        statement = (
            select(PhotoUploadRecord, PhotoUploadRevisionRecord)
            .join(
                PhotoUploadRevisionRecord,
                (PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id)
                & (PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version),
            )
            .outerjoin(
                PhotoAttemptRecord, PhotoAttemptRecord.id == PhotoUploadRevisionRecord.attempt_id
            )
            .where(
                PhotoUploadRecord.processing_expires_at > at,
                or_(
                    and_(
                        PhotoUploadRevisionRecord.state == "queued",
                        or_(
                            PhotoAttemptRecord.id.is_(None),
                            PhotoAttemptRecord.next_attempt_at <= at,
                        ),
                    ),
                    and_(
                        PhotoUploadRevisionRecord.state == "processing",
                        PhotoAttemptRecord.lease_until <= at,
                    ),
                ),
            )
            .order_by(PhotoUploadRecord.created_at, PhotoUploadRecord.id)
            .limit(1)
            .with_for_update(of=PhotoUploadRecord, skip_locked=True)
        )
        row = (await self.session.execute(statement)).one_or_none()
        if row is None:
            return None
        root, revision = row
        value = upload_value(root, revision)
        prior = (
            await self.session.get(PhotoAttemptRecord, value.attempt_id)
            if value.attempt_id is not None
            else None
        )
        if prior is not None:
            _finish(prior, "interrupted", at, PhotoFailure.PROCESSING_UNAVAILABLE)
        attempts = prior.number + 1 if prior is not None else 1
        if attempts > MAX_PHOTO_ATTEMPTS:
            await SqlMediaTransaction(self.session).save_upload(
                value.reject(PhotoFailure.PROCESSING_UNAVAILABLE, at)
            )
            return None
        attempt_id = uuid4()
        self.session.add(
            PhotoAttemptRecord(
                id=attempt_id,
                upload_id=value.id,
                number=attempts,
                started_at=at,
                lease_until=lease_until,
                outcome="processing",
            )
        )
        await self.session.flush()
        processing = value.processing(attempt_id, at)
        await SqlMediaTransaction(self.session).save_upload(processing)
        record_media_claim(
            value.id,
            value.account_id,
            attempt_id,
            attempts,
            await read_media_origin(self.session, value.id),
        )
        return PhotoLease(processing, attempt_id, attempts)

    async def is_current(self, lease: PhotoLease, at: datetime) -> bool:
        current = await SqlMediaTransaction(self.session).upload(
            lease.upload.account_id, lease.upload.id
        )
        attempt = await self.session.get(PhotoAttemptRecord, lease.attempt_id)
        return (
            current is not None
            and attempt is not None
            and _current(lease, current, attempt, at)
            and await self._allowed(lease)
        )

    async def _allowed(self, lease: PhotoLease) -> bool:
        return (
            await self.session.scalars(
                select(AccountRecord.id)
                .join(
                    InstitutionalBindingRecord,
                    InstitutionalBindingRecord.account_id == AccountRecord.id,
                )
                .where(
                    AccountRecord.id == lease.upload.account_id,
                    AccountRecord.deleted_at.is_(None),
                    AccountRecord.banned_at.is_(None),
                    InstitutionalBindingRecord.revoked_at.is_(None),
                )
            )
        ).one_or_none() is not None

    async def _locked(self, lease: PhotoLease) -> tuple[PhotoUpload, PhotoAttemptRecord] | None:
        await self.session.execute(
            select(AccountRecord.id)
            .where(AccountRecord.id == lease.upload.account_id)
            .with_for_update(key_share=True)
        )
        row = (
            await self.session.execute(
                select(PhotoUploadRecord, PhotoUploadRevisionRecord, PhotoAttemptRecord)
                .join(
                    PhotoUploadRevisionRecord,
                    (PhotoUploadRevisionRecord.upload_id == PhotoUploadRecord.id)
                    & (PhotoUploadRevisionRecord.version == PhotoUploadRecord.current_version),
                )
                .join(PhotoAttemptRecord, PhotoAttemptRecord.id == lease.attempt_id)
                .where(
                    PhotoUploadRecord.id == lease.upload.id,
                    PhotoUploadRecord.account_id == lease.upload.account_id,
                    PhotoAttemptRecord.upload_id == PhotoUploadRecord.id,
                )
                .with_for_update(of=(PhotoUploadRecord, PhotoAttemptRecord))
            )
        ).one_or_none()
        return (upload_value(row[0], row[1]), row[2]) if row is not None else None

    async def _stale(
        self,
        lease: PhotoLease,
        current: PhotoUpload,
        attempt: PhotoAttemptRecord,
        at: datetime,
        image: PhotoImageInfo | None = None,
    ) -> PhotoProcessingStep | None:
        if _current(lease, current, attempt, at):
            return None
        expired = current.expire(at)
        if expired is not current:
            await SqlMediaTransaction(self.session).save_upload(expired)
        _finish(attempt, "stale", at, image=image)
        return (
            PhotoProcessingStep.EXPIRED
            if expired.state == PhotoUploadState.EXPIRED
            else PhotoProcessingStep.STALE
        )

    async def complete(
        self, lease: PhotoLease, image: PhotoImageInfo, at: datetime
    ) -> PhotoProcessingStep:
        locked = await self._locked(lease)
        if locked is None:
            return PhotoProcessingStep.STALE
        current, attempt = locked
        at = max(at, await self.now())
        stale = await self._stale(lease, current, attempt, at, image)
        if stale is not None:
            return stale
        if not await self._allowed(lease):
            return await self._reject_current(
                current, attempt, PhotoFailure.ACCOUNT_UNAVAILABLE, at, image=image
            )
        photo = await SqlMediaTransaction(self.session).current_photo(current.account_id)
        version = photo.version if photo is not None else 0
        if version != current.expected_photo_version:
            return await self._reject_current(
                current, attempt, PhotoFailure.PHOTO_CHANGED, at, image=image
            )
        ready = current.ready(lease.attempt_id, at)
        await SqlMediaTransaction(self.session).save_upload(ready)
        published = PhotoRevision(current.account_id, version + 1, current.id, at)
        self.session.add(
            PhotoRevisionRecord(
                account_id=current.account_id,
                version=version + 1,
                upload_id=current.id,
                upload_version=ready.version,
                upload_state="ready",
                saved_at=at,
            )
        )
        await self.session.flush()
        if photo is None:
            self.session.add(
                PhotoRecord(account_id=current.account_id, current_version=version + 1)
            )
        else:
            await self.session.execute(
                update(PhotoRecord)
                .where(PhotoRecord.account_id == current.account_id)
                .values(current_version=version + 1)
            )
        _finish(attempt, "ready", at, image=image)
        await self.session.flush()
        await record_photo_published(self.session, published)
        return PhotoProcessingStep.READY

    async def _reject_current(
        self,
        current: PhotoUpload,
        attempt: PhotoAttemptRecord,
        reason: PhotoFailure,
        at: datetime,
        image: PhotoImageInfo | None = None,
    ) -> PhotoProcessingStep:
        await SqlMediaTransaction(self.session).save_upload(current.reject(reason, at))
        _finish(attempt, "rejected", at, reason, image=image)
        return PhotoProcessingStep.REJECTED

    async def reject(
        self,
        lease: PhotoLease,
        reason: PhotoFailure,
        at: datetime,
        retry_at: datetime | None = None,
    ) -> PhotoProcessingStep:
        locked = await self._locked(lease)
        if locked is None:
            return PhotoProcessingStep.STALE
        current, attempt = locked
        delay = max(retry_at - at, timedelta(seconds=1)) if retry_at is not None else None
        at = max(at, await self.now())
        stale = await self._stale(lease, current, attempt, at)
        if stale is not None:
            return stale
        if not await self._allowed(lease):
            reason, delay = PhotoFailure.ACCOUNT_UNAVAILABLE, None
        if (
            delay is not None
            and at + delay < current.processing_expires_at
            and attempt.number < MAX_PHOTO_ATTEMPTS
        ):
            await SqlMediaTransaction(self.session).save_upload(current.retry(at))
            _finish(attempt, "retry", at, reason)
            attempt.next_attempt_at = at + delay
            return PhotoProcessingStep.RETRY
        return await self._reject_current(current, attempt, reason, at)


def _current(
    lease: PhotoLease, value: PhotoUpload, attempt: PhotoAttemptRecord, at: datetime
) -> bool:
    return (
        value.state == PhotoUploadState.PROCESSING
        and value.attempt_id == lease.attempt_id
        and attempt.finished_at is None
        and attempt.lease_until > at
        and value.processing_expires_at > at
    )


def _finish(
    attempt: PhotoAttemptRecord,
    outcome: str,
    at: datetime,
    failure: PhotoFailure | None = None,
    *,
    image: PhotoImageInfo | None = None,
) -> None:
    if attempt.finished_at is not None:
        return
    attempt.outcome, attempt.finished_at = outcome, at
    attempt.failure = failure.value if failure is not None else None
    if image is not None:
        attempt.display_width, attempt.display_height = image.width, image.height
        attempt.display_size, attempt.display_digest = image.display_size, image.display_digest


@dataclass(frozen=True, slots=True)
class SqlPhotoWorkerUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PhotoWorkerTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlPhotoWorkerTransaction(session)
