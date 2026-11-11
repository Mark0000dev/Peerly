import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.idempotency import (
    IdempotencyConflictError,
    IntentFingerprinter,
    IntentKey,
)
from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.media import PhotoRevision, PhotoSource, PhotoUpload

UPLOAD_LIFETIME = timedelta(minutes=15)
PROCESSING_LIFETIME = timedelta(hours=1)
UPLOADS_PER_HOUR = 20
MAX_PENDING_UPLOADS = 3


class PhotoVersionConflictError(Exception):
    def __init__(self, version: int) -> None:
        super().__init__("Current photo has changed")
        self.current_version = version


class PhotoUploadUnavailableError(Exception):
    pass


class PhotoUploadRateLimitedError(Exception):
    def __init__(self, retry_at: datetime) -> None:
        super().__init__("Photo upload capacity exhausted")
        self.retry_at = retry_at


class UploadAction(StrEnum):
    FINALIZE = "finalize"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class UploadBudget:
    starts: int
    first_start_at: datetime | None
    pending: int
    next_pending_expiry: datetime | None


@dataclass(frozen=True, slots=True)
class MediaIntent:
    fingerprint: bytes = field(repr=False)
    upload_id: UUID
    result_version: int


class MediaTransaction(IdentityReader, Protocol):
    async def current_photo(self, account_id: UUID) -> PhotoRevision | None: ...

    async def upload(
        self, account_id: UUID, upload_id: UUID, version: int | None = None
    ) -> PhotoUpload | None: ...

    async def expire_pending_uploads(self, account_id: UUID, at: datetime) -> None: ...

    async def upload_budget(self, account_id: UUID, since: datetime) -> UploadBudget: ...

    async def media_intent(self, account_id: UUID, key: IntentKey) -> MediaIntent | None: ...

    async def create_upload(self, value: PhotoUpload) -> None: ...

    async def save_upload(self, value: PhotoUpload) -> None: ...

    async def remember_media_intent(
        self, account_id: UUID, key: IntentKey, intent: MediaIntent, at: datetime
    ) -> None: ...


class MediaUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[MediaTransaction]: ...


@dataclass(frozen=True, slots=True)
class StartPhotoCommand:
    credential: SessionCredential = field(repr=False)
    source: PhotoSource = field(repr=False)
    expected_photo_version: int
    intent_key: IntentKey

    def __post_init__(self) -> None:
        if isinstance(self.expected_photo_version, bool) or self.expected_photo_version < 0:
            raise ValueError("Expected photo version must be nonnegative")


@dataclass(frozen=True, slots=True)
class PhotoUploadCommand:
    credential: SessionCredential = field(repr=False)
    upload_id: UUID
    action: UploadAction
    intent_key: IntentKey


async def _replay(
    transaction: MediaTransaction, account_id: UUID, prior: MediaIntent, fingerprint: bytes
) -> PhotoUpload:
    if not hmac.compare_digest(prior.fingerprint, fingerprint):
        raise IdempotencyConflictError
    result = await transaction.upload(account_id, prior.upload_id, prior.result_version)
    if result is None:
        raise RuntimeError("Saved upload result is unavailable")
    return result


@dataclass(frozen=True, slots=True)
class StartPhotoUpload:
    unit_of_work: MediaUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: StartPhotoCommand) -> PhotoUpload:
        fingerprint = await self.fingerprinter.fingerprint(
            (
                "media.start.v1",
                str(command.expected_photo_version),
                str(command.source.size),
                command.source.content_type.value,
                command.source.sha256.hex(),
            )
        )
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            account_id = actor.session.account_id
            prior = await transaction.media_intent(account_id, command.intent_key)
            if prior is not None:
                return await _replay(transaction, account_id, prior, fingerprint)
            photo = await transaction.current_photo(account_id)
            version = photo.version if photo is not None else 0
            if version != command.expected_photo_version:
                raise PhotoVersionConflictError(version)
            await transaction.expire_pending_uploads(account_id, now)
            now = await transaction.now()
            budget = await transaction.upload_budget(account_id, now - timedelta(hours=1))
            retry = []
            if budget.starts >= UPLOADS_PER_HOUR:
                retry.append((budget.first_start_at or now) + timedelta(hours=1))
            if budget.pending >= MAX_PENDING_UPLOADS:
                retry.append(budget.next_pending_expiry or now + UPLOAD_LIFETIME)
            if retry:
                raise PhotoUploadRateLimitedError(max(retry))
            upload = PhotoUpload(
                uuid4(),
                account_id,
                command.source,
                version,
                now,
                now + UPLOAD_LIFETIME,
                now + PROCESSING_LIFETIME,
                now,
            )
            await transaction.create_upload(upload)
            await transaction.remember_media_intent(
                account_id,
                command.intent_key,
                MediaIntent(fingerprint, upload.id, upload.version),
                now,
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return upload


@dataclass(frozen=True, slots=True)
class ChangePhotoUpload:
    unit_of_work: MediaUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: PhotoUploadCommand) -> PhotoUpload:
        fingerprint = await self.fingerprinter.fingerprint(
            ("media." + command.action.value + ".v1", str(command.upload_id))
        )
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(command.credential)
            )
            account_id = actor.session.account_id
            prior = await transaction.media_intent(account_id, command.intent_key)
            if prior is not None:
                return await _replay(transaction, account_id, prior, fingerprint)
            current = await transaction.upload(account_id, command.upload_id)
            if current is None:
                raise PhotoUploadUnavailableError
            now = await transaction.now()
            result = (
                current.queue(now)
                if command.action == UploadAction.FINALIZE
                else current.cancel(now)
            )
            if result is not current:
                await transaction.save_upload(result)
            await transaction.remember_media_intent(
                account_id,
                command.intent_key,
                MediaIntent(fingerprint, result.id, result.version),
                now,
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result


@dataclass(frozen=True, slots=True)
class ReadOwnPhotoUpload:
    unit_of_work: MediaUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential, upload_id: UUID) -> PhotoUpload:
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            current = await transaction.upload(actor.session.account_id, upload_id)
            if current is None:
                raise PhotoUploadUnavailableError
            now = await transaction.now()
            if not actor.session.is_active(now):
                raise UnauthenticatedError
            result = current.expire(now)
            if result is not current:
                await transaction.save_upload(result)
            return result
