"""Real preparation/codec/retention checks; no chat message is sent by READY."""

import asyncio
import hashlib
from contextlib import suppress
from dataclasses import replace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.application.chat_images.finalize import FinalizeChatImage, FinalizeChatImageCommand
from studymate.application.chat_images.worker import ChatImageProcessingStep, ProcessNextChatImage
from studymate.application.idempotency import IntentKey
from studymate.application.messaging.commands import CancelMessageCommand
from studymate.domain.chat_images import ChatImagePreparation
from studymate.domain.media import MediaObjectKind, PhotoContentType, PhotoSource
from studymate.infrastructure.chat_images.finalize import SqlChatImageFinalizeUnitOfWork
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.worker import SqlChatImageWorkerUnitOfWork
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.media_models import PhotoRevisionRecord
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.image_fixture import encoded
from tests.integration.media_fixture import Storage
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_chat_image_start import start, submission
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration


async def queued(engine: AsyncEngine, data: bytes) -> tuple[Chat, ChatImagePreparation]:
    owned = await chat(engine)
    image = await start(owned)(
        replace(
            submission(owned),
            source=PhotoSource(
                len(data),
                hashlib.sha256(data).digest(),
                PhotoContentType.PNG,
            ),
        )
    )
    image = await FinalizeChatImage(
        SqlChatImageFinalizeUnitOfWork(owned.api.sessions, record_message_outcome),
        HASHER,
        FINGERPRINTER,
    )(
        FinalizeChatImageCommand(
            owned.sender.credential,
            image.conversation_id,
            image.id,
            IntentKey("actual-worker-image-finalize"),
        )
    )
    return owned, image


async def test_worker_prepares_real_sanitized_rendition_without_sending_or_profile_publication(
    identity_engine: AsyncEngine,
) -> None:
    data = encoded()
    owned, image = await queued(identity_engine, data)
    storage, processor = Storage(data), BoundedImageProcessor()
    async with owned.api.sessions() as session:
        photos_before = await session.scalar(select(func.count()).select_from(PhotoRevisionRecord))
    try:
        result = await ProcessNextChatImage(
            SqlChatImageWorkerUnitOfWork(owned.api.sessions), storage, processor
        )()
    finally:
        await processor.close()
    assert result == ChatImageProcessingStep.READY
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == "ready"
        attempt = await session.get(ChatImageAttemptRecord, current.attempt_id)
        assert attempt is not None
        assert attempt.outcome == "ready"
        assert attempt.display_digest is not None
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(PhotoRevisionRecord))
            == photos_before
        )
    assert {reference.kind for reference in storage.retained} == {
        MediaObjectKind.ORIGINAL,
        MediaObjectKind.DISPLAY,
    }
    assert any(
        body.startswith(b"\xff\xd8\xff")
        for reference, body in storage.retained.items()
        if reference.kind == MediaObjectKind.DISPLAY
    )


async def test_real_cancel_during_storage_io_fences_late_output_and_releases_sql(
    identity_engine: AsyncEngine,
) -> None:
    data = encoded()
    owned, image = await queued(identity_engine, data)
    storage, processor = Storage(data), BoundedImageProcessor()
    storage.pause = True
    task = asyncio.create_task(
        ProcessNextChatImage(SqlChatImageWorkerUnitOfWork(owned.api.sessions), storage, processor)()
    )
    try:
        await asyncio.wait_for(storage.started.wait(), timeout=5)
        assert isinstance(identity_engine.pool, AsyncAdaptedQueuePool)
        assert identity_engine.pool.checkedout() == 0
        outcome = await owned.cancel()(
            CancelMessageCommand(
                owned.sender.credential,
                image.conversation_id,
                image.client_message_id,
                IntentKey("cancel-during-worker-io"),
            )
        )
        assert outcome.cancelled_at is not None
        storage.release.set()
        assert await asyncio.wait_for(task, timeout=5) == ChatImageProcessingStep.STALE
    finally:
        storage.release.set()
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await processor.close()
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == "cancelled"
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0
        attempt = (await session.scalars(select(ChatImageAttemptRecord))).one()
        assert attempt.outcome == "interrupted"
    assert {reference.kind for reference in storage.retained} == {
        MediaObjectKind.ORIGINAL,
        MediaObjectKind.DISPLAY,
    }


async def test_changed_source_is_rejected_without_retained_or_confirmed_data(
    identity_engine: AsyncEngine,
) -> None:
    owned, image = await queued(identity_engine, encoded())
    storage, processor = Storage(b"changed-private-source"), BoundedImageProcessor()
    try:
        assert (
            await ProcessNextChatImage(
                SqlChatImageWorkerUnitOfWork(owned.api.sessions), storage, processor
            )()
            == ChatImageProcessingStep.REJECTED
        )
    finally:
        await processor.close()
    assert not storage.retained
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == "rejected"
        assert current.failure == "content_changed"
