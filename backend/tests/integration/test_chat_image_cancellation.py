from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.chat_images.finalize import FinalizeChatImage, FinalizeChatImageCommand
from studymate.application.idempotency import IntentKey
from studymate.application.messaging.commands import CancelMessageCommand
from studymate.domain.chat_images import ChatImagePreparation
from studymate.infrastructure.chat_images.finalize import SqlChatImageFinalizeUnitOfWork
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.revisions import save_image_revision
from studymate.infrastructure.persistence.message_models import MessageOperationRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_chat_image_start import revision, start, submission
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration


async def image_state(owned: Chat, state: str) -> ChatImagePreparation:
    image = await start(owned)(submission(owned))
    if state == "uploading":
        return image
    queued = await FinalizeChatImage(
        SqlChatImageFinalizeUnitOfWork(owned.api.sessions, record_message_outcome),
        HASHER,
        FINGERPRINTER,
    )(
        FinalizeChatImageCommand(
            owned.sender.credential,
            image.conversation_id,
            image.id,
            IntentKey("queue-before-cancel"),
        )
    )
    if state == "queued":
        return queued
    processing = queued.claim(uuid4(), queued.updated_at)
    assert processing.attempt_id is not None
    final = (
        processing.ready(processing.attempt_id, processing.updated_at)
        if state == "ready"
        else (processing.retry(processing.updated_at) if state == "retry" else processing)
    )
    async with owned.api.sessions.begin() as session:
        session.add(
            ChatImageAttemptRecord(
                id=processing.attempt_id,
                image_id=image.id,
                number=1,
                started_at=processing.updated_at,
                lease_until=processing.updated_at + timedelta(minutes=2),
                finished_at=None if state == "processing" else processing.updated_at,
                next_attempt_at=processing.updated_at + timedelta(seconds=2)
                if state == "retry"
                else None,
                outcome={"processing": "processing", "ready": "ready", "retry": "retry"}[state],
                display_width=1 if state == "ready" else None,
                display_height=1 if state == "ready" else None,
                display_size=1 if state == "ready" else None,
                display_digest=b"d" * 32 if state == "ready" else None,
            )
        )
        await session.flush()
        session.add(revision(processing))
        if final != processing:
            session.add(revision(final))
        await session.flush()
        await session.execute(
            update(ChatImageRecord)
            .where(ChatImageRecord.id == image.id)
            .values(current_version=final.version)
        )
    return final


@pytest.mark.parametrize("state", ["uploading", "queued", "processing", "retry", "ready"])
async def test_actual_cancel_atomically_closes_pending_preparation_without_destroying_ready_source(
    identity_engine: AsyncEngine,
    state: str,
) -> None:
    owned = await chat(identity_engine)
    image = await image_state(owned, state)
    command = CancelMessageCommand(
        owned.sender.credential,
        image.conversation_id,
        image.client_message_id,
        IntentKey("cancel-image-atomically"),
    )
    outcome = await owned.cancel()(command)
    assert outcome.cancelled_at is not None
    assert await owned.cancel()(command) == outcome
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == ("ready" if state == "ready" else "cancelled")
        assert root.current_version == image.version + (0 if state == "ready" else 1)
        assert (
            await session.scalar(select(func.count()).select_from(ChatImageRevisionRecord))
            == root.current_version
        )
        if image.attempt_id is not None:
            attempt = await session.get(ChatImageAttemptRecord, image.attempt_id)
            assert attempt is not None
            assert (
                attempt.outcome
                == {"processing": "interrupted", "retry": "retry", "ready": "ready"}[state]
            )
            assert attempt.finished_at == (
                outcome.cancelled_at if state == "processing" else image.updated_at
            )


async def test_failed_cleanup_rolls_back_terminal_message_canonical_and_image_revision_together(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned = await chat(identity_engine)
    image = await image_state(owned, "queued")
    async with owned.api.sessions() as session:
        events_before = await session.scalar(select(func.count()).select_from(ProductEventRecord))

    async def fail_after_revision(session: AsyncSession, value: ChatImagePreparation) -> None:
        await save_image_revision(session, value)
        raise RuntimeError("Synthetic cleanup write failure")

    monkeypatch.setattr(
        "studymate.infrastructure.chat_images.cancellation.save_image_revision", fail_after_revision
    )
    with pytest.raises(RuntimeError, match="cleanup write failure"):
        await owned.cancel()(
            CancelMessageCommand(
                owned.sender.credential,
                image.conversation_id,
                image.client_message_id,
                IntentKey("failed-atomic-cancel"),
            )
        )
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        assert root.current_version == image.version
        assert await session.scalar(select(func.count()).select_from(MessageOperationRecord)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(ProductEventRecord))
            == events_before
        )
        assert (
            await session.scalar(select(func.count()).select_from(ChatImageRevisionRecord))
            == image.version
        )
