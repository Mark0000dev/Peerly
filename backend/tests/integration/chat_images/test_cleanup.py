"""Transport-only cleanup on actual image lifecycle state and durable lease metadata."""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.chat_images.worker import ChatImageLease
from studymate.application.media.cleanup import (
    CleanupMediaTransport,
    TransportCleanupLease,
    TransportCleanupStep,
)
from studymate.domain.media import MediaObjectKind
from studymate.infrastructure.chat_images.cleanup import SqlImageCleanupUnitOfWork
from studymate.infrastructure.chat_images.cleanup_models import ChatImageTransportCleanupRecord
from studymate.infrastructure.chat_images.models import ChatImageRecord, ChatImageRevisionRecord
from studymate.infrastructure.chat_images.worker import SqlChatImageWorkerUnitOfWork
from tests.image_fixture import encoded
from tests.integration.chat_images.test_display import prepared
from tests.integration.media_fixture import Storage
from tests.integration.test_chat_image_start import start, submission
from tests.integration.test_chat_image_worker import queued
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration


def unit(owned: Chat) -> SqlImageCleanupUnitOfWork:
    return SqlImageCleanupUnitOfWork(owned.api.sessions)


def cleaner(owned: Chat, storage: Storage) -> CleanupMediaTransport:
    return CleanupMediaTransport(unit(owned), storage)


async def age_transport(owned: Chat, *, processing_expired: bool = False) -> None:
    async with owned.api.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(ChatImageRecord).values(
                created_at=now - timedelta(hours=2),
                upload_expires_at=now - timedelta(minutes=30),
                processing_expires_at=now - timedelta(seconds=1)
                if processing_expired
                else now + timedelta(minutes=30),
            )
        )
        await session.execute(
            update(ChatImageTransportCleanupRecord).values(
                next_attempt_at=now - timedelta(seconds=1)
            )
        )


@pytest.mark.parametrize("processing", [False, True])
async def test_cleanup_never_removes_valid_queued_or_processing_transport(
    identity_engine: AsyncEngine, processing: bool
) -> None:
    owned, image = await queued(identity_engine, encoded())
    if processing:
        async with SqlChatImageWorkerUnitOfWork(owned.api.sessions).transaction() as tx:
            now = await tx.now()
            lease = await tx.claim(now, now + timedelta(minutes=2))
            assert isinstance(lease, ChatImageLease)
    storage = Storage(b"")
    cleanup = cleaner(owned, storage)
    assert await cleanup() == TransportCleanupStep.IDLE
    await age_transport(owned)
    assert await cleanup() == TransportCleanupStep.IDLE
    assert not storage.removed
    await age_transport(owned, processing_expired=True)
    assert await cleanup() == TransportCleanupStep.CLEANED
    assert len(storage.removed) == 1
    assert storage.removed[0].upload_id == image.id
    assert storage.removed[0].kind == MediaObjectKind.UPLOAD


async def test_cleanup_preserves_retained_original_display_and_all_revision_history(
    identity_engine: AsyncEngine,
) -> None:
    owned, image, storage = await prepared(identity_engine)
    retained = storage.retained.copy()
    cleanup = cleaner(owned, storage)
    assert await cleanup() == TransportCleanupStep.IDLE
    async with owned.api.sessions() as session:
        count_before = await session.scalar(
            select(func.count()).select_from(ChatImageRevisionRecord)
        )
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        version_before = root.current_version
    await age_transport(owned)
    assert await cleanup() == TransportCleanupStep.CLEANED
    assert await cleanup() == TransportCleanupStep.IDLE
    assert storage.retained == retained
    assert {ref.kind for ref in retained} == {MediaObjectKind.ORIGINAL, MediaObjectKind.DISPLAY}
    assert len(storage.removed) == 1
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        assert root.current_version == version_before
        assert (
            await session.scalar(select(func.count()).select_from(ChatImageRevisionRecord))
            == count_before
        )
        record = await session.get(ChatImageTransportCleanupRecord, image.id)
        assert record is not None
        assert record.cleaned_at is not None
        assert record.generation is None
        assert record.lease_until is None


async def test_expired_abandoned_upload_is_claimed_once_by_competing_workers(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))
    await age_transport(owned)
    storage = Storage(b"")
    outcomes = await asyncio.gather(cleaner(owned, storage)(), cleaner(owned, storage)())
    assert set(outcomes) == {TransportCleanupStep.CLEANED, TransportCleanupStep.IDLE}
    assert [reference.upload_id for reference in storage.removed] == [image.id]


async def test_storage_outage_retains_backoff_and_can_retry_without_history_loss(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))
    await age_transport(owned)
    storage = Storage(b"", unavailable=True)
    cleanup = cleaner(owned, storage)
    assert await cleanup() == TransportCleanupStep.RETRY
    assert await cleanup() == TransportCleanupStep.IDLE
    async with owned.api.sessions.begin() as session:
        record = await session.get(ChatImageTransportCleanupRecord, image.id)
        assert record is not None
        assert record.attempts == 1
        assert record.cleaned_at is None
        assert record.generation is None
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        assert record.next_attempt_at > now
        record.next_attempt_at = now - timedelta(seconds=1)
    storage.unavailable = False
    assert await cleanup() == TransportCleanupStep.CLEANED


async def test_reclaimed_generation_fences_old_expired_and_duplicate_ack(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))
    await age_transport(owned)
    uow = unit(owned)
    async with uow.transaction() as tx:
        now = await tx.now()
        first = await tx.claim(now, now + timedelta(minutes=1))
    assert first is not None
    async with owned.api.sessions.begin() as session:
        await session.execute(
            update(ChatImageTransportCleanupRecord)
            .where(ChatImageTransportCleanupRecord.image_id == image.id)
            .values(lease_until=func.clock_timestamp() - timedelta(seconds=1))
        )
    async with uow.transaction() as tx:
        assert not await tx.finish(first, await tx.now(), None)
        now = await tx.now()
        second = await tx.claim(now, now + timedelta(minutes=1))
    assert second is not None
    assert second.generation != first.generation
    async with uow.transaction() as tx:
        assert not await tx.finish(first, await tx.now(), None)
        assert await tx.finish(second, await tx.now(), None)
    async with uow.transaction() as tx:
        assert not await tx.finish(second, await tx.now(), None)
        assert not await tx.finish(TransportCleanupLease(uuid4(), uuid4(), 1), await tx.now(), None)


async def test_claim_failure_rolls_back_generation_and_attempt_counter(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))
    await age_transport(owned)

    async def failed_claim() -> None:
        async with unit(owned).transaction() as tx:
            now = await tx.now()
            assert await tx.claim(now, now + timedelta(minutes=1)) is not None
            raise RuntimeError("synthetic transaction failure")

    with pytest.raises(RuntimeError, match="synthetic transaction"):
        await failed_claim()
    async with owned.api.sessions() as session:
        record = await session.get(ChatImageTransportCleanupRecord, image.id)
        assert record is not None
        assert record.attempts == 0
        assert record.generation is None
        assert record.lease_until is None
    assert await cleaner(owned, Storage(b""))() == TransportCleanupStep.CLEANED


@pytest.mark.parametrize("was_queued", [False, True])
async def test_cleanup_claim_uses_actual_first_queue_origin_without_ambient_fallback(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    was_queued: bool,
) -> None:
    from uuid import UUID

    from studymate.application.ports.http_tracing import HttpExecution
    from studymate.infrastructure.observability.origin import ExecutionOrigin
    from studymate.infrastructure.observability.tracing import OtelHttpTracing

    request_id, action_id = uuid4(), uuid4()
    tracing = OtelHttpTracing()
    with tracing.start(HttpExecution(request_id, action_id, "POST", None)):
        if was_queued:
            owned, image = await queued(identity_engine, encoded())
        else:
            owned = await chat(identity_engine)
            image = await start(owned)(submission(owned))
    claims: list[ExecutionOrigin | None] = []

    def capture(
        image_id: UUID,
        account_id: UUID,
        generation: UUID,
        attempts: int,
        origin: ExecutionOrigin | None,
    ) -> None:
        assert image_id == image.id
        assert account_id == owned.sender.id
        assert generation.int > 0
        assert attempts == 1
        claims.append(origin)

    monkeypatch.setattr("studymate.infrastructure.chat_images.cleanup.record_media_claim", capture)
    await age_transport(owned, processing_expired=True)
    with tracing.start(HttpExecution(uuid4(), uuid4(), "POST", None)):
        assert await cleaner(owned, Storage(b""))() == TransportCleanupStep.CLEANED
    expected = ExecutionOrigin(request_id, action_id, None, None) if was_queued else None
    assert claims == [expected]
