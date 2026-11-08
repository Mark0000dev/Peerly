from dataclasses import dataclass
from uuid import UUID

from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.media.storage import MediaReader, MediaStorage, UploadAccess
from studymate.application.media.uploads import MediaUnitOfWork, PhotoUploadUnavailableError
from studymate.domain.media import MediaObjectKind, MediaObjectRef, PhotoUploadState


class PhotoUploadAccessDeniedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CreatePhotoUploadAccess:
    unit_of_work: MediaUnitOfWork
    hasher: SessionHasher
    storage: MediaStorage

    async def __call__(self, credential: SessionCredential, upload_id: UUID) -> UploadAccess:
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
            effective = current.expire(now)
            if effective is not current:
                await transaction.save_upload(effective)
        # Expiration is committed even when access cannot be granted.
        if effective.state != PhotoUploadState.UPLOADING:
            raise PhotoUploadAccessDeniedError
        return await self.storage.upload_access(
            MediaObjectRef(upload_id, MediaObjectKind.UPLOAD),
            effective.source.content_type.value,
            effective.upload_expires_at,
        )


@dataclass(frozen=True, slots=True)
class ReadOwnPhotoDisplay:
    unit_of_work: MediaUnitOfWork
    hasher: SessionHasher
    storage: MediaReader

    async def __call__(self, credential: SessionCredential, upload_id: UUID) -> bytes:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            current = await transaction.upload(actor.session.account_id, upload_id)
            if (
                current is None
                or current.state != PhotoUploadState.READY
                or current.attempt_id is None
            ):
                raise PhotoUploadUnavailableError
            reference = MediaObjectRef(upload_id, MediaObjectKind.DISPLAY, current.attempt_id)
        return await self.storage.read(reference)
