import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.chat_images.finalize import (
    ChatImageUnavailableError,
    FinalizeChatImage,
    FinalizeChatImageCommand,
)
from studymate.application.chat_images.start import ChatImageIntent, ChatImageMessageResolvedError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.messaging.commands import CancelMessageCommand
from studymate.domain.chat_images import ChatImageState
from studymate.infrastructure.chat_images.finalize import (
    SqlChatImageFinalizeTransaction,
    SqlChatImageFinalizeUnitOfWork,
)
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageIntentRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_chat_image_start import revision, start, submission
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration
FINAL_REVISION = 2
PARALLEL_FINALIZATIONS = 6


async def test_parallel_finalize_replays_exact_queued_revision_without_messages(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))
    finalize = FinalizeChatImage(
        SqlChatImageFinalizeUnitOfWork(owned.api.sessions, record_message_outcome),
        HASHER,
        FINGERPRINTER,
    )
    command = FinalizeChatImageCommand(
        owned.sender.credential, image.conversation_id, image.id, IntentKey("finalize-real-image")
    )
    results = await asyncio.gather(*(finalize(command) for _ in range(PARALLEL_FINALIZATIONS)))
    assert all(result == results[0] for result in results)
    assert results[0].state == ChatImageState.QUEUED
    assert results[0].version == FINAL_REVISION
    with pytest.raises(IdempotencyConflictError):
        await finalize(replace(command, image_id=uuid4()))
    with pytest.raises(ChatImageUnavailableError):
        await finalize(
            replace(command, image_id=uuid4(), intent_key=IntentKey("unknown-source-image"))
        )
    with pytest.raises(ChatImageUnavailableError):
        await finalize(replace(command, credential=owned.recipient.credential))
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(ChatImageRevisionRecord))
            == FINAL_REVISION
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ChatImageIntentRecord)
                .where(ChatImageIntentRecord.operation == "finalize")
            )
            == 1
        )


async def test_real_cancel_tombstone_prevents_late_image_queue(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))
    outcome = await owned.cancel()(
        CancelMessageCommand(
            owned.sender.credential,
            image.conversation_id,
            image.client_message_id,
            IntentKey("cancel-image-message"),
        )
    )
    finalize = FinalizeChatImage(
        SqlChatImageFinalizeUnitOfWork(owned.api.sessions, record_message_outcome),
        HASHER,
        FINGERPRINTER,
    )
    with pytest.raises(ChatImageMessageResolvedError) as error:
        await finalize(
            FinalizeChatImageCommand(
                owned.sender.credential,
                image.conversation_id,
                image.id,
                IntentKey("late-image-finalize"),
            )
        )
    assert error.value.operation == outcome
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == "cancelled"
        assert tuple(
            await session.scalars(
                select(ChatImageRevisionRecord.state).order_by(ChatImageRevisionRecord.version)
            )
        ) == ("uploading", "cancelled")
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0


async def test_postwrite_expiry_rolls_back_queue_and_receipt(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))
    original = SqlChatImageFinalizeTransaction.remember_image_finalize
    original_now = SqlChatImageFinalizeTransaction.now
    expired = False

    async def expire_after_write(
        transaction: SqlChatImageFinalizeTransaction,
        actor_id: UUID,
        key: IntentKey,
        intent: ChatImageIntent,
        at: datetime,
    ) -> None:
        nonlocal expired
        await original(transaction, actor_id, key, intent, at)
        expired = True

    async def clock(transaction: SqlChatImageFinalizeTransaction) -> datetime:
        if expired:
            expiry = await transaction.session.scalar(
                select(SessionRecord.expires_at).where(SessionRecord.account_id == owned.sender.id)
            )
            assert expiry is not None
            return expiry
        return await original_now(transaction)

    monkeypatch.setattr(
        SqlChatImageFinalizeTransaction, "remember_image_finalize", expire_after_write
    )
    monkeypatch.setattr(SqlChatImageFinalizeTransaction, "now", clock)
    finalize = FinalizeChatImage(
        SqlChatImageFinalizeUnitOfWork(owned.api.sessions, record_message_outcome),
        HASHER,
        FINGERPRINTER,
    )
    with pytest.raises(UnauthenticatedError):
        await finalize(
            FinalizeChatImageCommand(
                owned.sender.credential,
                image.conversation_id,
                image.id,
                IntentKey("expiry-image-finalize"),
            )
        )
    async with owned.api.sessions() as session:
        assert await session.scalar(select(ChatImageRevisionRecord.state)) == "uploading"
        assert await session.scalar(select(func.count()).select_from(ChatImageRevisionRecord)) == 1


@pytest.mark.parametrize("attempt_outcome", ["processing", "interrupted"])
async def test_elapsed_processing_retains_attempt_and_original_finalize_receipt(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    attempt_outcome: str,
) -> None:
    owned = await chat(identity_engine)
    image = await start(owned)(submission(owned))
    finalize = FinalizeChatImage(
        SqlChatImageFinalizeUnitOfWork(owned.api.sessions, record_message_outcome),
        HASHER,
        FINGERPRINTER,
    )
    command = FinalizeChatImageCommand(
        owned.sender.credential,
        image.conversation_id,
        image.id,
        IntentKey("first-finalize-receipt"),
    )
    queued = await finalize(command)
    processing = queued.claim(uuid4(), queued.updated_at)
    async with owned.api.sessions.begin() as session:
        session.add(
            ChatImageAttemptRecord(
                id=processing.attempt_id,
                image_id=image.id,
                number=1,
                started_at=processing.updated_at,
                lease_until=processing.updated_at + timedelta(minutes=2),
                finished_at=processing.updated_at if attempt_outcome == "interrupted" else None,
                outcome=attempt_outcome,
            )
        )
        await session.flush()
        session.add(revision(processing))
        await session.flush()
        await session.execute(
            update(ChatImageRecord)
            .where(ChatImageRecord.id == image.id)
            .values(current_version=processing.version)
        )

    async def elapsed(_transaction: SqlChatImageFinalizeTransaction) -> datetime:
        return image.processing_expires_at

    monkeypatch.setattr(SqlChatImageFinalizeTransaction, "now", elapsed)
    expired = await finalize(replace(command, intent_key=IntentKey("resolve-expired-image")))
    assert expired.state == ChatImageState.EXPIRED
    assert await finalize(command) == queued
    async with owned.api.sessions() as session:
        attempt = await session.get(ChatImageAttemptRecord, processing.attempt_id)
        assert attempt is not None
        assert attempt.outcome == "interrupted"
        assert attempt.finished_at == (
            image.processing_expires_at
            if attempt_outcome == "processing"
            else processing.updated_at
        )
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0
