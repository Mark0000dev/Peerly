import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
    UploadAccess,
)
from studymate.application.media.uploads import (
    ChangePhotoUpload,
    PhotoUploadCommand,
    ReadOwnPhotoUpload,
    StartPhotoCommand,
    StartPhotoUpload,
    UploadAction,
)
from studymate.application.media.worker import ProcessNextPhoto
from studymate.domain.media import (
    MediaObjectKind,
    MediaObjectRef,
    PhotoContentType,
    PhotoSource,
    PhotoUpload,
)
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.media_uploads import SqlMediaUnitOfWork
from studymate.infrastructure.persistence.photo_worker import SqlPhotoWorkerUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.student_actor import Actor


def services(engine: AsyncEngine) -> tuple[StartPhotoUpload, ChangePhotoUpload, ReadOwnPhotoUpload]:
    uow = SqlMediaUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    hasher = Sha256SessionHasher()
    fingerprint = HmacIntentFingerprinter(bytes(range(32)))
    return (
        StartPhotoUpload(uow, hasher, fingerprint),
        ChangePhotoUpload(uow, hasher, fingerprint),
        ReadOwnPhotoUpload(uow, hasher),
    )


def command(owner: Actor, *, version: int = 0) -> StartPhotoCommand:
    return StartPhotoCommand(
        owner.credential,
        PhotoSource(10, bytes(range(32)), PhotoContentType.PNG),
        version,
        IntentKey(str(uuid4())),
    )


@dataclass(slots=True)
class Storage:
    data: bytes = field(repr=False)
    retained: dict[MediaObjectRef, bytes] = field(default_factory=dict, repr=False)
    pause: bool = False
    unavailable: bool = False
    started: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    removed: list[MediaObjectRef] = field(default_factory=list)
    accesses: list[tuple[MediaObjectRef, str, datetime]] = field(default_factory=list)

    async def upload_access(
        self, reference: MediaObjectRef, content_type: str, expires_at: datetime
    ) -> UploadAccess:
        if self.unavailable:
            raise MediaStorageUnavailableError
        self.accesses.append((reference, content_type, expires_at))
        return UploadAccess(
            "https://storage.example.test/synthetic",
            (("key", str(reference.upload_id)), ("policy", "synthetic-policy")),
        )

    async def read(self, reference: MediaObjectRef) -> bytes:
        if reference.kind != MediaObjectKind.UPLOAD:
            if reference not in self.retained:
                raise MediaObjectMissingError
            return self.retained[reference]
        self.started.set()
        if self.pause:
            await self.release.wait()
        if self.unavailable:
            raise MediaStorageUnavailableError
        if not self.data:
            raise MediaObjectMissingError
        return self.data

    async def retain(self, reference: MediaObjectRef, data: bytes, content_type: str) -> None:
        assert reference.kind != MediaObjectKind.UPLOAD
        assert content_type in {"image/png", "image/jpeg"}
        assert reference not in self.retained
        self.retained[reference] = data

    async def remove_transport(self, reference: MediaObjectRef) -> None:
        assert reference.kind == MediaObjectKind.UPLOAD
        if self.unavailable:
            raise MediaStorageUnavailableError
        self.removed.append(reference)


async def queued(engine: AsyncEngine, owner: Actor, data: bytes) -> PhotoUpload:
    start, change, _ = services(engine)
    uploaded = await start(
        StartPhotoCommand(
            owner.credential,
            PhotoSource(len(data), hashlib.sha256(data).digest(), PhotoContentType.PNG),
            0,
            IntentKey(str(uuid4())),
        )
    )
    return await change(
        PhotoUploadCommand(
            owner.credential, uploaded.id, UploadAction.FINALIZE, IntentKey(str(uuid4()))
        )
    )


def worker(
    engine: AsyncEngine, storage: Storage, processor: BoundedImageProcessor
) -> ProcessNextPhoto:
    return ProcessNextPhoto(
        SqlPhotoWorkerUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        storage,
        processor,
    )
