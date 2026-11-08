from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.media.resume import PhotoResumeTransaction, ReadOwnPhotoResume
from studymate.domain.media import PhotoContentType, PhotoRevision, PhotoSource, PhotoUpload
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.photo: PhotoRevision | None = None
        self.uploads: tuple[PhotoUpload, ...] = ()
        self.expire_when_read = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PhotoResumeTransaction]:
        yield self

    async def current_photo(self, account_id: UUID) -> PhotoRevision | None:
        assert account_id == self.actor.session.account_id
        return self.photo

    async def expire_pending_uploads(self, account_id: UUID, at: datetime) -> None:
        assert account_id == self.actor.session.account_id
        assert at == self.clock

    async def resume_uploads(
        self, account_id: UUID, current_upload_id: UUID | None
    ) -> tuple[PhotoUpload, ...]:
        assert account_id == self.actor.session.account_id
        assert current_upload_id == (self.photo.upload_id if self.photo is not None else None)
        if self.expire_when_read:
            self.clock = self.actor.session.expires_at
        return self.uploads


def upload(account_id: UUID) -> PhotoUpload:
    return PhotoUpload(
        uuid4(),
        account_id,
        PhotoSource(10, bytes(32), PhotoContentType.PNG),
        0,
        NOW,
        NOW + timedelta(minutes=15),
        NOW + timedelta(hours=1),
        NOW,
    )


async def test_verified_nonactivated_student_can_resume_without_saving_profile() -> None:
    store = Store()
    store.uploads = (upload(store.actor.session.account_id),)
    result = await ReadOwnPhotoResume(store, Sha256SessionHasher())(CREDENTIAL)
    assert result.photo is None
    assert result.uploads == store.uploads
    assert not store.actor.activation_complete


@pytest.mark.parametrize("state", ["unverified", "banned", "deleted"])
async def test_photo_resume_checks_current_membership_and_lifecycle(state: str) -> None:
    store = Store()
    store.actor = replace(
        store.actor,
        membership=None if state == "unverified" else store.actor.membership,
        banned=state == "banned",
        deleted_at=NOW if state == "deleted" else None,
    )
    with pytest.raises(UnauthenticatedError if state == "deleted" else StudentActionDeniedError):
        await ReadOwnPhotoResume(store, Sha256SessionHasher())(CREDENTIAL)


async def test_photo_resume_rejects_foreign_upload_projection() -> None:
    store = Store()
    store.uploads = (upload(uuid4()),)
    with pytest.raises(RuntimeError, match="another account"):
        await ReadOwnPhotoResume(store, Sha256SessionHasher())(CREDENTIAL)


async def test_photo_resume_checks_session_expiry_after_loading_projection() -> None:
    store = Store()
    store.expire_when_read = True
    with pytest.raises(UnauthenticatedError):
        await ReadOwnPhotoResume(store, Sha256SessionHasher())(CREDENTIAL)


async def test_photo_resume_rejects_foreign_current_photo_projection() -> None:
    store = Store()
    store.photo = PhotoRevision(uuid4(), 1, uuid4(), NOW)
    with pytest.raises(RuntimeError, match="another account"):
        await ReadOwnPhotoResume(store, Sha256SessionHasher())(CREDENTIAL)
