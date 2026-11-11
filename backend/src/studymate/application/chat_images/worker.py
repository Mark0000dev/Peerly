"""Bounded conversation-image preparation; READY never sends a message."""

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
from studymate.domain.chat_images import ChatImageFailure, ChatImagePreparation, ChatImageState
from studymate.domain.media import MediaObjectKind, MediaObjectRef

MAX_ATTEMPTS = 3
EXPIRY_BATCH = 100


class ChatImageProcessingStep(StrEnum):
    IDLE = "idle"
    BUSY = "busy"
    READY = "ready"
    RETRY = "retry"
    REJECTED = "rejected"
    EXPIRED = "expired"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class ChatImageLease:
    image: ChatImagePreparation = field(repr=False)
    attempt_id: UUID
    attempts: int

    def __post_init__(self) -> None:
        if isinstance(self.attempts, bool) or not 1 <= self.attempts <= MAX_ATTEMPTS:
            raise ValueError("Chat image lease requires an actual bounded attempt")
        if (
            self.image.state != ChatImageState.PROCESSING
            or self.image.attempt_id != self.attempt_id
        ):
            raise ValueError("Chat image lease must reference its actual source attempt")


@dataclass(frozen=True, slots=True)
class ChatImageInfo:
    width: int
    height: int
    display_size: int
    display_digest: bytes = field(repr=False)


class ChatImageWorkerTransaction(Protocol):
    async def now(self) -> datetime: ...

    async def expire_images(self, at: datetime, batch: int) -> None: ...

    async def claim(
        self, at: datetime, lease_until: datetime
    ) -> ChatImageLease | ChatImageProcessingStep | None: ...

    async def preflight(
        self, lease: ChatImageLease, at: datetime
    ) -> ChatImageProcessingStep | None: ...

    async def complete(
        self, lease: ChatImageLease, image: ChatImageInfo, at: datetime
    ) -> ChatImageProcessingStep: ...

    async def reject(
        self,
        lease: ChatImageLease,
        reason: ChatImageFailure,
        at: datetime,
        retry_at: datetime | None = None,
    ) -> ChatImageProcessingStep: ...


class ChatImageWorkerUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[ChatImageWorkerTransaction]: ...


@dataclass(frozen=True, slots=True)
class ChatImageWorkerPolicy:
    lease_duration: timedelta = timedelta(seconds=120)
    processing_timeout: timedelta = timedelta(seconds=90)
    retry_delays: tuple[timedelta, ...] = (timedelta(seconds=2), timedelta(seconds=10))

    def __post_init__(self) -> None:
        if not timedelta() < self.processing_timeout < self.lease_duration:
            raise ValueError("Image processing timeout must fit inside its lease")
        if len(self.retry_delays) != MAX_ATTEMPTS - 1 or any(
            delay <= timedelta() for delay in self.retry_delays
        ):
            raise ValueError("Chat image retries must be positive and bounded")


@dataclass(frozen=True, slots=True)
class ProcessNextChatImage:
    unit_of_work: ChatImageWorkerUnitOfWork
    storage: MediaStorage
    processor: ImageProcessor
    policy: ChatImageWorkerPolicy = ChatImageWorkerPolicy()

    async def __call__(self) -> ChatImageProcessingStep:
        if not self.processor.available:
            return ChatImageProcessingStep.BUSY
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            await transaction.expire_images(now, EXPIRY_BATCH)
            lease = await transaction.claim(now, now + self.policy.lease_duration)
        if isinstance(lease, ChatImageProcessingStep):
            return lease
        if lease is None:
            return ChatImageProcessingStep.IDLE
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            unavailable = await transaction.preflight(lease, now)
            if unavailable is not None:
                return unavailable
        failure: ChatImageFailure | None = None
        permanent = False
        processed: ProcessedImage | None = None
        try:
            async with asyncio.timeout(self.policy.processing_timeout.total_seconds()):
                processed = await self._process(lease)
        except InvalidImageError as error:
            failure, permanent = ChatImageFailure(error.reason.value), True
        except (MediaStorageUnavailableError, MediaObjectMissingError):
            failure = ChatImageFailure.STORAGE_UNAVAILABLE
        except (TimeoutError, ImageProcessorUnavailableError):
            failure = ChatImageFailure.PROCESSING_UNAVAILABLE
        except _ContentChangedError:
            failure, permanent = ChatImageFailure.CONTENT_CHANGED, True
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            if failure is None:
                if processed is None:
                    raise RuntimeError("Completed image preparation lacks its actual rendition")
                return await transaction.complete(
                    lease,
                    ChatImageInfo(
                        processed.width,
                        processed.height,
                        len(processed.data),
                        hashlib.sha256(processed.data).digest(),
                    ),
                    now,
                )
            retry_at = None
            if not permanent and lease.attempts < MAX_ATTEMPTS:
                retry_at = now + self.policy.retry_delays[lease.attempts - 1]
            return await transaction.reject(lease, failure, now, retry_at)

    async def _process(self, lease: ChatImageLease) -> ProcessedImage:
        image = lease.image
        data = await self.storage.read(MediaObjectRef(image.id, MediaObjectKind.UPLOAD))
        if len(data) != image.source.size or not hmac.compare_digest(
            hashlib.sha256(data).digest(), image.source.sha256
        ):
            raise _ContentChangedError
        processed = await self.processor.process(data)
        if processed.source_content_type != image.source.content_type:
            raise _ContentChangedError
        await self.storage.retain(
            MediaObjectRef(image.id, MediaObjectKind.ORIGINAL, lease.attempt_id),
            data,
            image.source.content_type.value,
        )
        await self.storage.retain(
            MediaObjectRef(image.id, MediaObjectKind.DISPLAY, lease.attempt_id),
            processed.data,
            processed.content_type,
        )
        return processed


class _ContentChangedError(Exception):
    pass
