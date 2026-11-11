"""Recover owner photo work without persisting browser files or upload tickets."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.domain.media import PhotoRevision, PhotoUpload

RECENT_TERMINAL_UPLOADS = 20


@dataclass(frozen=True, slots=True)
class OwnPhotoResume:
    photo: PhotoRevision | None
    uploads: tuple[PhotoUpload, ...]


class PhotoResumeTransaction(IdentityReader, Protocol):
    async def current_photo(self, account_id: UUID) -> PhotoRevision | None: ...

    async def expire_pending_uploads(self, account_id: UUID, at: datetime) -> None: ...

    async def resume_uploads(
        self, account_id: UUID, current_upload_id: UUID | None
    ) -> tuple[PhotoUpload, ...]: ...


class PhotoResumeUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[PhotoResumeTransaction]: ...


@dataclass(frozen=True, slots=True)
class ReadOwnPhotoResume:
    unit_of_work: PhotoResumeUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential) -> OwnPhotoResume:
        async with self.unit_of_work.transaction() as transaction:
            actor, now = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            account_id = actor.session.account_id
            await transaction.expire_pending_uploads(account_id, now)
            photo = await transaction.current_photo(account_id)
            uploads = await transaction.resume_uploads(
                account_id, photo.upload_id if photo is not None else None
            )
            if photo is not None and photo.account_id != account_id:
                raise RuntimeError("Current photo projection belongs to another account")
            if any(upload.account_id != account_id for upload in uploads):
                raise RuntimeError("Photo resume projection belongs to another account")
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return OwnPhotoResume(photo, uploads)
