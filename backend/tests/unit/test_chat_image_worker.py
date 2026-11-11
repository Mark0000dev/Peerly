"""Image worker invariants with controlled storage/codec boundaries."""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from studymate.application.chat_images.worker import (
    ChatImageInfo,
    ChatImageLease,
    ChatImageProcessingStep,
    ChatImageWorkerPolicy,
    ChatImageWorkerTransaction,
    ProcessNextChatImage,
)
from studymate.application.media.processing import (
    ImageFailure,
    ImageProcessorUnavailableError,
    InvalidImageError,
    ProcessedImage,
)
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
    UploadAccess,
)
from studymate.domain.chat_images import ChatImageFailure, ChatImagePreparation
from studymate.domain.media import MediaObjectKind, MediaObjectRef, PhotoContentType, PhotoSource
from tests.unit.identity_store import NOW

SQL_PHASES = 3
SOURCE = b"private-synthetic-image-source"
DISPLAY = b"sanitized-synthetic-display"


class Store:
    def __init__(self) -> None:
        image = (
            ChatImagePreparation(
                uuid4(),
                uuid4(),
                uuid4(),
                uuid4(),
                PhotoSource(len(SOURCE), hashlib.sha256(SOURCE).digest(), PhotoContentType.PNG),
                NOW,
                NOW + timedelta(minutes=15),
                NOW + timedelta(hours=1),
                NOW,
            )
            .queue(NOW)
            .claim(uuid4(), NOW)
        )
        assert image.attempt_id is not None
        self.lease: ChatImageLease | None = ChatImageLease(image, image.attempt_id, 1)
        self.claim_result: ChatImageProcessingStep | None = None
        self.inside = False
        self.transactions = 0
        self.preflight_result: ChatImageProcessingStep | None = None
        self.final_result = ChatImageProcessingStep.READY
        self.rejections: list[tuple[ChatImageFailure, datetime | None]] = []
        self.completed: ChatImageInfo | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[ChatImageWorkerTransaction]:
        assert not self.inside
        self.inside = True
        self.transactions += 1
        try:
            yield self
        finally:
            self.inside = False

    async def now(self) -> datetime:
        return NOW

    async def expire_images(self, at: datetime, batch: int) -> None:
        assert at == NOW
        assert batch > 0

    async def claim(
        self, at: datetime, lease_until: datetime
    ) -> ChatImageLease | ChatImageProcessingStep | None:
        assert at == NOW
        assert lease_until > at
        return self.claim_result if self.claim_result is not None else self.lease

    async def preflight(
        self, lease: ChatImageLease, at: datetime
    ) -> ChatImageProcessingStep | None:
        assert lease == self.lease
        assert at == NOW
        return self.preflight_result

    async def complete(
        self, lease: ChatImageLease, image: ChatImageInfo, at: datetime
    ) -> ChatImageProcessingStep:
        assert lease == self.lease
        assert at == NOW
        self.completed = image
        return self.final_result

    async def reject(
        self,
        lease: ChatImageLease,
        reason: ChatImageFailure,
        at: datetime,
        retry_at: datetime | None = None,
    ) -> ChatImageProcessingStep:
        assert lease == self.lease
        assert at == NOW
        self.rejections.append((reason, retry_at))
        return ChatImageProcessingStep.RETRY if retry_at else ChatImageProcessingStep.REJECTED


class Storage:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.data = SOURCE
        self.mode = "ready"
        self.retained: dict[MediaObjectRef, bytes] = {}
        self.reads = 0

    async def upload_access(
        self, reference: MediaObjectRef, content_type: str, expires_at: datetime
    ) -> UploadAccess:
        raise AssertionError(
            f"Worker cannot mint {reference.kind}/{content_type} access "
            f"before {expires_at.isoformat()}"
        )

    async def read(self, reference: MediaObjectRef) -> bytes:
        assert not self.store.inside
        assert reference.kind == MediaObjectKind.UPLOAD
        self.reads += 1
        if self.mode == "missing":
            raise MediaObjectMissingError
        if self.mode == "unavailable":
            raise MediaStorageUnavailableError
        if self.mode == "cancelled":
            raise asyncio.CancelledError
        if self.mode == "timeout":
            await asyncio.Event().wait()
        return self.data

    async def retain(self, reference: MediaObjectRef, data: bytes, content_type: str) -> None:
        assert not self.store.inside
        assert content_type in ("image/png", "image/jpeg")
        if self.mode == "display_failed" and reference.kind == MediaObjectKind.DISPLAY:
            raise MediaStorageUnavailableError
        self.retained[reference] = data

    async def remove_transport(self, reference: MediaObjectRef) -> None:
        raise AssertionError(f"Worker cannot purge retained {reference.kind} source")


class Processor:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.available = True
        self.mode = "ready"
        self.source_type = PhotoContentType.PNG

    async def process(self, data: bytes) -> ProcessedImage:
        assert not self.store.inside
        assert data == SOURCE
        if self.mode == "invalid":
            raise InvalidImageError(ImageFailure.ANIMATED_IMAGE)
        if self.mode == "unavailable":
            raise ImageProcessorUnavailableError
        return ProcessedImage(DISPLAY, 800, 400, source_content_type=self.source_type)


async def test_ready_retains_exact_source_and_display_outside_sql_without_delivery() -> None:
    store = Store()
    storage, processor = (Storage(store), Processor(store))
    assert await ProcessNextChatImage(store, storage, processor)() == ChatImageProcessingStep.READY
    assert store.completed == ChatImageInfo(
        800, 400, len(DISPLAY), hashlib.sha256(DISPLAY).digest()
    )
    assert set(storage.retained.values()) == {SOURCE, DISPLAY}
    assert store.transactions == SQL_PHASES
    assert not store.inside
    assert not store.rejections


@pytest.mark.parametrize("mode", ["busy", "idle", "preflight", "claim_settled"])
async def test_no_storage_work_when_capacity_or_actual_source_prevents_processing(
    mode: str,
) -> None:
    store = Store()
    storage, processor = (Storage(store), Processor(store))
    expected = ChatImageProcessingStep.REJECTED
    if mode == "busy":
        processor.available = False
        expected = ChatImageProcessingStep.BUSY
    elif mode == "idle":
        store.lease = None
        expected = ChatImageProcessingStep.IDLE
    elif mode == "claim_settled":
        store.claim_result = expected
    else:
        store.preflight_result = expected
    assert await ProcessNextChatImage(store, storage, processor)() == expected
    assert storage.reads == 0
    assert not storage.retained


@pytest.mark.parametrize("mode", ["missing", "unavailable", "display_failed", "timeout"])
async def test_transient_io_failure_retries_boundedly_without_ready_or_sql_across_io(
    mode: str,
) -> None:
    store = Store()
    storage, processor = (Storage(store), Processor(store))
    storage.mode = mode
    policy = ChatImageWorkerPolicy(processing_timeout=timedelta(milliseconds=5))
    assert (
        await ProcessNextChatImage(store, storage, processor, policy)()
        == ChatImageProcessingStep.RETRY
    )
    assert store.completed is None
    assert not store.inside
    assert store.rejections[0][1] == NOW + timedelta(seconds=2)
    if mode == "display_failed":
        assert tuple(storage.retained.values()) == (SOURCE,)


@pytest.mark.parametrize(
    "mode", ["bytes", "type", "invalid", "processor_unavailable", "last_attempt"]
)
async def test_source_validation_and_attempt_limit_control_retry(mode: str) -> None:
    store = Store()
    storage, processor = (Storage(store), Processor(store))
    expected = ChatImageProcessingStep.REJECTED
    if mode == "bytes":
        storage.data = b"changed-source"
    elif mode == "type":
        processor.source_type = PhotoContentType.JPEG
    elif mode == "invalid":
        processor.mode = "invalid"
    elif mode == "processor_unavailable":
        processor.mode = "unavailable"
        expected = ChatImageProcessingStep.RETRY
    else:
        assert store.lease is not None
        store.lease = replace(store.lease, attempts=3)
        storage.mode = "unavailable"
    assert await ProcessNextChatImage(store, storage, processor)() == expected
    assert store.completed is None


async def test_cancellation_propagates_for_durable_lease_recovery() -> None:
    store = Store()
    storage, processor = (Storage(store), Processor(store))
    storage.mode = "cancelled"
    with pytest.raises(asyncio.CancelledError):
        await ProcessNextChatImage(store, storage, processor)()
    assert not store.rejections
    assert store.completed is None
    assert not store.inside


async def test_final_source_fence_can_discard_a_prepared_rendition() -> None:
    store = Store()
    storage, processor = (Storage(store), Processor(store))
    store.final_result = ChatImageProcessingStep.STALE
    assert await ProcessNextChatImage(store, storage, processor)() == ChatImageProcessingStep.STALE
    assert set(storage.retained.values()) == {SOURCE, DISPLAY}


@pytest.mark.parametrize("timeout", [timedelta(), timedelta(seconds=-1), timedelta(seconds=120)])
def test_worker_timeout_must_fit_actual_lease(timeout: timedelta) -> None:
    with pytest.raises(ValueError, match="fit inside its lease"):
        ChatImageWorkerPolicy(processing_timeout=timeout)


@pytest.mark.parametrize(
    "delays", [(), (timedelta(seconds=1),), (timedelta(), timedelta(seconds=1))]
)
def test_worker_retry_schedule_cannot_exceed_attempt_capacity(
    delays: tuple[timedelta, ...],
) -> None:
    with pytest.raises(ValueError, match="positive and bounded"):
        ChatImageWorkerPolicy(retry_delays=delays)


@pytest.mark.parametrize("attempts", [True, 0, 4])
def test_actual_lease_cannot_admit_boolean_or_out_of_range_attempt(attempts: int) -> None:
    lease = Store().lease
    assert lease is not None
    with pytest.raises(ValueError, match="actual bounded attempt"):
        replace(lease, attempts=attempts)


@pytest.mark.parametrize("mode", ["wrong_attempt", "wrong_state"])
def test_lease_is_bound_to_actual_processing_revision(mode: str) -> None:
    lease = Store().lease
    assert lease is not None
    attempt_id = uuid4() if mode == "wrong_attempt" else lease.attempt_id
    image = lease.image if mode == "wrong_attempt" else lease.image.ready(lease.attempt_id, NOW)
    with pytest.raises(ValueError, match="actual source attempt"):
        replace(lease, attempt_id=attempt_id, image=image)
