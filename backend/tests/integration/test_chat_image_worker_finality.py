from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.chat_images.worker import (
    ChatImageInfo,
    ChatImageLease,
    ChatImageProcessingStep,
)
from studymate.domain.chat_images import ChatImageFailure
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.worker import (
    SqlChatImageWorkerTransaction,
    SqlChatImageWorkerUnitOfWork,
)
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.message_models import (
    MessageOperationRecord,
    MessageRecord,
)
from tests.image_fixture import encoded
from tests.integration.test_chat_image_worker import queued
from tests.integration.test_chat_image_worker_leases import claim

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("phase", ["preflight", "complete", "reject"])
async def test_current_ban_stops_each_worker_phase_and_retains_actual_output_metadata(
    identity_engine: AsyncEngine, phase: str
) -> None:
    owned, image = await queued(identity_engine, encoded())
    unit = SqlChatImageWorkerUnitOfWork(owned.api.sessions)
    lease = await claim(unit)
    assert isinstance(lease, ChatImageLease)
    async with owned.api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owned.recipient.id)
            .values(banned_at=func.clock_timestamp())
        )
    output = ChatImageInfo(1, 1, 1, b"r" * 32)
    async with unit.transaction() as transaction:
        at = await transaction.now()
        if phase == "preflight":
            result = await transaction.preflight(lease, at)
        elif phase == "complete":
            result = await transaction.complete(lease, output, at)
        else:
            result = await transaction.reject(lease, ChatImageFailure.STORAGE_UNAVAILABLE, at)
    assert result == ChatImageProcessingStep.REJECTED
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        revision = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        attempt = await session.get(ChatImageAttemptRecord, lease.attempt_id)
        assert revision is not None
        assert attempt is not None
        assert revision.state == "rejected"
        assert revision.failure == "contact_unavailable"
        assert attempt.outcome == "rejected"
        assert attempt.display_digest == (output.display_digest if phase == "complete" else None)


@pytest.mark.parametrize("phase", ["maintenance", "preflight", "complete", "reject"])
async def test_processing_deadline_settles_expired_without_ready_publication(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    owned, image = await queued(identity_engine, encoded())
    unit = SqlChatImageWorkerUnitOfWork(owned.api.sessions)
    lease = await claim(unit)
    assert isinstance(lease, ChatImageLease)
    deadline = image.processing_expires_at

    async def clock(_transaction: SqlChatImageWorkerTransaction) -> datetime:
        return deadline

    monkeypatch.setattr(SqlChatImageWorkerTransaction, "now", clock)
    async with unit.transaction() as transaction:
        if phase == "maintenance":
            await transaction.expire_images(deadline, 10)
        elif phase == "preflight":
            assert await transaction.preflight(lease, deadline) == ChatImageProcessingStep.EXPIRED
        elif phase == "complete":
            assert (
                await transaction.complete(lease, ChatImageInfo(1, 1, 1, b"e" * 32), deadline)
                == ChatImageProcessingStep.EXPIRED
            )
        else:
            assert (
                await transaction.reject(lease, ChatImageFailure.STORAGE_UNAVAILABLE, deadline)
                == ChatImageProcessingStep.EXPIRED
            )
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        attempt = await session.get(ChatImageAttemptRecord, lease.attempt_id)
        assert current is not None
        assert attempt is not None
        assert current.state == "expired"
        assert attempt.outcome in {"stale", "interrupted"}
        assert attempt.display_digest == (b"e" * 32 if phase == "complete" else None)


@pytest.mark.parametrize("locked_resource", ["account", "conversation", "image"])
async def test_worker_skips_busy_authority_and_claims_after_transaction_releases(
    identity_engine: AsyncEngine, locked_resource: str
) -> None:
    owned, image = await queued(identity_engine, encoded())
    unit = SqlChatImageWorkerUnitOfWork(owned.api.sessions)
    async with owned.api.sessions.begin() as blocker:
        if locked_resource == "account":
            await blocker.scalar(
                select(AccountRecord.id)
                .where(AccountRecord.id == image.account_id)
                .with_for_update()
            )
        elif locked_resource == "conversation":
            await blocker.scalar(
                select(ConversationRecord.id)
                .where(ConversationRecord.id == image.conversation_id)
                .with_for_update()
            )
        else:
            await blocker.scalar(
                select(ChatImageRecord.id).where(ChatImageRecord.id == image.id).with_for_update()
            )
        assert await claim(unit) is None
    assert isinstance(await claim(unit), ChatImageLease)


async def test_existing_confirmed_message_intent_stops_unpublished_preparation(
    identity_engine: AsyncEngine,
) -> None:
    owned, image = await queued(identity_engine, encoded())
    # A retained text intent from before image admission was enforced remains
    # authoritative; processing must not retroactively attach the queued file.
    operation_id, message_id = uuid4(), uuid4()
    async with owned.api.sessions.begin() as session:
        conversation = await session.get(ConversationRecord, image.conversation_id)
        assert conversation is not None
        session.add(
            MessageOperationRecord(
                id=operation_id,
                conversation_id=image.conversation_id,
                low_id=conversation.low_id,
                high_id=conversation.high_id,
                author_id=image.account_id,
                client_message_id=image.client_message_id,
                state="confirmed",
                message_id=message_id,
            )
        )
        await session.flush()
        session.add(
            MessageRecord(
                id=message_id,
                operation_id=operation_id,
                conversation_id=image.conversation_id,
                low_id=conversation.low_id,
                high_id=conversation.high_id,
                author_id=image.account_id,
                client_message_id=image.client_message_id,
                state="confirmed",
                sequence=1,
                text="Retained legacy text intent, not an image attachment",
                sent_at=image.updated_at,
            )
        )
        await session.execute(
            update(ConversationRecord)
            .where(ConversationRecord.id == image.conversation_id)
            .values(next_message_sequence=2)
        )
    assert (
        await claim(SqlChatImageWorkerUnitOfWork(owned.api.sessions))
        == ChatImageProcessingStep.STALE
    )
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == "cancelled"
        assert current.attempt_id is None


@pytest.mark.parametrize("retry_beyond_expiry", [False, True])
async def test_permanent_or_impossible_retry_rejects_and_replay_cannot_publish_ready(
    identity_engine: AsyncEngine, retry_beyond_expiry: bool
) -> None:
    owned, image = await queued(identity_engine, encoded())
    unit = SqlChatImageWorkerUnitOfWork(owned.api.sessions)
    lease = await claim(unit)
    assert isinstance(lease, ChatImageLease)
    async with unit.transaction() as transaction:
        at = await transaction.now()
        result = await transaction.reject(
            lease,
            ChatImageFailure.CONTENT_CHANGED,
            at,
            image.processing_expires_at if retry_beyond_expiry else None,
        )
        assert result == ChatImageProcessingStep.REJECTED
    async with unit.transaction() as transaction:
        assert (
            await transaction.complete(
                lease, ChatImageInfo(1, 1, 1, b"s" * 32), await transaction.now()
            )
            == ChatImageProcessingStep.STALE
        )
    assert await claim(unit) is None
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        attempt = await session.get(ChatImageAttemptRecord, lease.attempt_id)
        assert current is not None
        assert attempt is not None
        assert current.state == "rejected"
        assert current.failure == "content_changed"
        assert attempt.outcome == "rejected"
        assert attempt.next_attempt_at is None


async def test_admission_snapshot_cannot_start_processing_after_deadline_elapsed_before_lock(
    identity_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned, image = await queued(identity_engine, encoded())
    unit = SqlChatImageWorkerUnitOfWork(owned.api.sessions)

    async def clock(_transaction: SqlChatImageWorkerTransaction) -> datetime:
        return image.processing_expires_at

    monkeypatch.setattr(SqlChatImageWorkerTransaction, "now", clock)
    async with unit.transaction() as transaction:
        result = await transaction.claim(image.updated_at, image.processing_expires_at)
    assert result == ChatImageProcessingStep.EXPIRED
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == "expired"
        assert current.attempt_id is None
