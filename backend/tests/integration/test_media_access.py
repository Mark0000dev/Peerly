from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.media.access import (
    CreatePhotoUploadAccess,
    PhotoUploadAccessDeniedError,
    ReadOwnPhotoDisplay,
)
from studymate.application.media.uploads import PhotoUploadUnavailableError
from studymate.domain.media import MediaObjectKind, PhotoUploadState
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.media_models import PhotoUploadRecord
from studymate.infrastructure.persistence.media_uploads import SqlMediaUnitOfWork
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.image_fixture import encoded
from tests.integration.media_fixture import Storage, command, queued, services, worker
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_upload_grant_uses_owned_live_intent_and_original_absolute_deadline(
    identity_engine: AsyncEngine,
) -> None:
    owner, other = await actor(identity_engine), await actor(identity_engine)
    start, _, _ = services(identity_engine)
    upload = await start(command(owner))
    storage = Storage(b"")
    access = CreatePhotoUploadAccess(
        SqlMediaUnitOfWork(async_sessionmaker(identity_engine)), Sha256SessionHasher(), storage
    )
    result = await access(owner.credential, upload.id)
    assert result.fields
    assert storage.accesses[0][0].kind == MediaObjectKind.UPLOAD
    assert storage.accesses[0][0].upload_id == upload.id
    assert storage.accesses[0][2] == upload.upload_expires_at
    with pytest.raises(PhotoUploadUnavailableError):
        await access(other.credential, upload.id)
    with pytest.raises(PhotoUploadUnavailableError):
        await access(owner.credential, uuid4())


async def test_expired_grant_commits_expiration_before_reporting_denial(
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine)
    start, _, read = services(identity_engine)
    upload = await start(command(owner))
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(PhotoUploadRecord).values(
                created_at=func.clock_timestamp() - timedelta(minutes=20),
                upload_expires_at=func.clock_timestamp() - timedelta(minutes=5),
            )
        )
    storage = Storage(b"")
    access = CreatePhotoUploadAccess(
        SqlMediaUnitOfWork(async_sessionmaker(identity_engine)), Sha256SessionHasher(), storage
    )
    with pytest.raises(PhotoUploadAccessDeniedError):
        await access(owner.credential, upload.id)
    assert storage.accesses == []
    assert (await read(owner.credential, upload.id)).state == PhotoUploadState.EXPIRED


async def test_own_display_requires_owned_ready_processed_reference(
    identity_engine: AsyncEngine,
) -> None:
    owner, other = await actor(identity_engine), await actor(identity_engine)
    data = encoded()
    upload = await queued(identity_engine, owner, data)
    storage = Storage(data)
    read = ReadOwnPhotoDisplay(
        SqlMediaUnitOfWork(async_sessionmaker(identity_engine)), Sha256SessionHasher(), storage
    )
    with pytest.raises(PhotoUploadUnavailableError):
        await read(owner.credential, upload.id)
    processor = BoundedImageProcessor()
    try:
        await worker(identity_engine, storage, processor)()
    finally:
        await processor.close()
    assert (await read(owner.credential, upload.id)).startswith(b"\xff\xd8\xff")
    with pytest.raises(PhotoUploadUnavailableError):
        await read(other.credential, upload.id)
    access = CreatePhotoUploadAccess(
        SqlMediaUnitOfWork(async_sessionmaker(identity_engine)), Sha256SessionHasher(), storage
    )
    with pytest.raises(PhotoUploadAccessDeniedError):
        await access(owner.credential, upload.id)
