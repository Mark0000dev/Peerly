"""One bounded durable photo step; no storage/codec I/O under a SQL transaction."""

import asyncio
import hashlib
import hmac
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from studymate.application.media.processing import (
    ImageProcessor,
    ImageProcessorUnavailableError,
    InvalidImageError,
    ProcessedImage,
)
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorage,
    MediaStorageUnavailableError,
)
from studymate.domain.media import MediaObjectKind, MediaObjectRef, PhotoFailure, PhotoUpload

MAX_PHOTO_ATTEMPTS = 3
EXPIRY_BATCH = 100


class PhotoProcessingStep(StrEnum):
    IDLE = "idle"
    BUSY = "busy"
    READY = "ready"
    RETRY = "retry"
    REJECTED = "rejected"
    EXPIRED = "expired"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class PhotoLease:
    upload: PhotoUpload = field(repr=False)
    attempt_id: UUID
    attempts: int


@dataclass(frozen=True, slots=True)
class PhotoImageInfo:
    width: int
    height: int
    display_size: int
    display_digest: bytes = field(repr=False)


class PhotoWorkerTransaction(Protocol):
    async def now(self) -> datetime: ...

    async def expire_uploads(self, at: datetime, batch: int) -> None: ...

    async def claim(self, at: datetime, lease_until: datetime) -> PhotoLease | None: ...

    async def is_current(self, lease: PhotoLease, at: datetime) -> bool: ...

    async def complete(
        self, lease: PhotoLease, image: PhotoImageInfo, at: datetime
    ) -> PhotoProcessingStep: ...

    async def reject(
        self,
        lease: PhotoLease,
        reason: PhotoFailure,
        at: datetime,
        retry_at: datetime | None = None,
    ) -> PhotoProcessingStep: ...


class PhotoWorkerUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[PhotoWorkerTransaction]: ...


@dataclass(frozen=True, slots=True)
class PhotoWorkerPolicy:
    lease_duration: timedelta = timedelta(seconds=120)
    processing_timeout: timedelta = timedelta(seconds=90)
    retry_delays: tuple[timedelta, ...] = (timedelta(seconds=2), timedelta(seconds=10))

    def __post_init__(self) -> None:
        if not timedelta() < self.processing_timeout < self.lease_duration:
            raise ValueError("Photo processing timeout must be positive and shorter than its lease")
        if len(self.retry_delays) != MAX_PHOTO_ATTEMPTS - 1 or any(
            delay <= timedelta() for delay in self.retry_delays
        ):
            raise ValueError("Photo retries must be positive and bounded")


@dataclass(frozen=True, slots=True)
class ProcessNextPhoto:
    unit_of_work: PhotoWorkerUnitOfWork
    storage: MediaStorage
    processor: ImageProcessor
    policy: PhotoWorkerPolicy = PhotoWorkerPolicy()

    async def __call__(self) -> PhotoProcessingStep:
        if not self.processor.available:
            return PhotoProcessingStep.BUSY
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            await transaction.expire_uploads(now, EXPIRY_BATCH)
            lease = await transaction.claim(now, now + self.policy.lease_duration)
        if lease is None:
            return PhotoProcessingStep.IDLE
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            if not await transaction.is_current(lease, now):
                return await transaction.reject(lease, PhotoFailure.ACCOUNT_UNAVAILABLE, now)
        failure: PhotoFailure | None = None
        permanent = False
        processed: ProcessedImage | None = None
        try:
            async with asyncio.timeout(self.policy.processing_timeout.total_seconds()):
                processed = await self._process(lease)
        except InvalidImageError as error:
            failure, permanent = PhotoFailure(error.reason.value), True
        except (MediaStorageUnavailableError, MediaObjectMissingError):
            failure = PhotoFailure.STORAGE_UNAVAILABLE
        except (TimeoutError, ImageProcessorUnavailableError):
            failure = PhotoFailure.PROCESSING_UNAVAILABLE
        except _ContentChangedError:
            failure, permanent = PhotoFailure.CONTENT_CHANGED, True
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            if failure is None:
                if processed is None:
                    raise RuntimeError("Completed photo lacks its processed output")
                info = PhotoImageInfo(
                    processed.width,
                    processed.height,
                    len(processed.data),
                    hashlib.sha256(processed.data).digest(),
                )
                return await transaction.complete(lease, info, now)
            retry_at = None
            if not permanent and lease.attempts < MAX_PHOTO_ATTEMPTS:
                retry_at = now + self.policy.retry_delays[lease.attempts - 1]
            return await transaction.reject(lease, failure, now, retry_at)

    async def _process(self, lease: PhotoLease) -> ProcessedImage:
        source = lease.upload.source
        data = await self.storage.read(MediaObjectRef(lease.upload.id, MediaObjectKind.UPLOAD))
        if len(data) != source.size or not hmac.compare_digest(
            hashlib.sha256(data).digest(), source.sha256
        ):
            raise _ContentChangedError
        processed = await self.processor.process(data)
        if processed.source_content_type != source.content_type:
            raise _ContentChangedError
        await self.storage.retain(
            MediaObjectRef(lease.upload.id, MediaObjectKind.ORIGINAL, lease.attempt_id),
            data,
            source.content_type.value,
        )
        await self.storage.retain(
            MediaObjectRef(lease.upload.id, MediaObjectKind.DISPLAY, lease.attempt_id),
            processed.data,
            processed.content_type,
        )
        return processed


class _ContentChangedError(Exception):
    pass
