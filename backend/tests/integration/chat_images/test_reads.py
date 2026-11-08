"""Bounded recovery from actual retained image/message records, with no storage calls."""

from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.chat_images.finalize import ChatImageUnavailableError
from studymate.application.chat_images.reads import (
    OWNED_IMAGE_LIMIT,
    ListOwnImagePreparations,
    ReadOwnedImagePreparation,
)
from studymate.application.chat_images.worker import ProcessNextChatImage
from studymate.application.idempotency import IntentKey
from studymate.application.messaging.commands import CancelMessageCommand, authorize_conversation
from studymate.domain.chat_images import ChatImageState
from studymate.domain.messaging import MessageOutcome
from studymate.infrastructure.chat_images.models import ChatImageRecord, ChatImageRevisionRecord
from studymate.infrastructure.chat_images.reads import SqlImageReadUnitOfWork
from studymate.infrastructure.chat_images.revisions import save_image_revision
from studymate.infrastructure.chat_images.start import SqlChatImageStartTransaction
from studymate.infrastructure.chat_images.worker import SqlChatImageWorkerUnitOfWork
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.image_fixture import encoded
from tests.integration.media_fixture import Storage
from tests.integration.requests.fixture import HASHER
from tests.integration.test_chat_image_start import start, submission
from tests.integration.test_chat_image_worker import queued
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration


def unit(owned: Chat) -> SqlImageReadUnitOfWork:
    return SqlImageReadUnitOfWork(owned.api.sessions, record_message_outcome)


async def test_owned_reload_effective_expiry_never_writes_revision_event_or_activity(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    source = await start(owned)(submission(owned))
    async with owned.api.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(ChatImageRecord)
            .where(ChatImageRecord.id == source.id)
            .values(
                created_at=now - timedelta(minutes=20),
                upload_expires_at=now - timedelta(seconds=1),
            )
        )
    async with owned.api.sessions() as session:
        events_before = await session.scalar(select(func.count()).select_from(ProductEventRecord))
        activity_before = await session.scalar(
            select(DiscoveryExposureRecord.last_activity_at).where(
                DiscoveryExposureRecord.account_id == owned.sender.id
            )
        )
    read, listing = (
        ReadOwnedImagePreparation(unit(owned), HASHER),
        ListOwnImagePreparations(unit(owned), HASHER),
    )
    result = await read(owned.sender.credential, owned.conversation_id, source.id)
    assert result.preparation.version == source.version
    assert result.preparation.state == ChatImageState.UPLOADING
    assert result.effective_state == ChatImageState.EXPIRED
    assert await listing(owned.sender.credential, owned.conversation_id) == (result,)
    assert not await listing(owned.recipient.credential, owned.conversation_id)
    with pytest.raises(ChatImageUnavailableError):
        await read(owned.recipient.credential, owned.conversation_id, source.id)
    with pytest.raises(ChatImageUnavailableError):
        await read(owned.sender.credential, owned.conversation_id, uuid4())
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, source.id)
        assert root is not None
        assert root.current_version == source.version
        assert await session.scalar(select(func.count()).select_from(ChatImageRevisionRecord)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ProductEventRecord))
            == events_before
        )
        assert (
            await session.scalar(
                select(DiscoveryExposureRecord.last_activity_at).where(
                    DiscoveryExposureRecord.account_id == owned.sender.id
                )
            )
            == activity_before
        )


async def test_actual_ready_attempt_and_cancel_outcome_are_returned_without_attachment_claim(
    identity_engine: AsyncEngine,
) -> None:
    data = encoded()
    owned, source = await queued(identity_engine, data)
    processor = BoundedImageProcessor()
    try:
        await ProcessNextChatImage(
            SqlChatImageWorkerUnitOfWork(owned.api.sessions), Storage(data), processor
        )()
    finally:
        await processor.close()
    operation = await owned.cancel()(
        CancelMessageCommand(
            owned.sender.credential,
            owned.conversation_id,
            source.client_message_id,
            IntentKey("read-ready-cancel"),
        )
    )
    result = await ReadOwnedImagePreparation(unit(owned), HASHER)(
        owned.sender.credential, owned.conversation_id, source.id
    )
    assert result.effective_state == ChatImageState.READY
    assert result.ready is not None
    assert result.ready.attempt_id == result.preparation.attempt_id
    assert result.ready.width > 0
    assert result.ready.height > 0
    assert result.ready.size > 0
    assert result.message_outcome is not None
    assert result.message_outcome.id == operation.id
    assert result.message_outcome.outcome == MessageOutcome.CANCELLED
    assert result.message_outcome.message_id is None


async def test_list_keeps_pending_roots_and_only_twenty_latest_terminal_sources(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    original = await start(owned)(submission(owned))
    # Retained business fixture uses actual authorized source/revision adapters;
    # it is not a claim that intake rate limits permit this burst of new starts.
    async with owned.api.sessions.begin() as session:
        tx = SqlChatImageStartTransaction(session, owned.conversation_id, record_message_outcome)
        await authorize_conversation(tx, HASHER, owned.sender.credential, owned.conversation_id)
        for _ in range(22):
            image = replace(original, id=uuid4(), client_message_id=uuid4())
            await tx.create_image(image)
            await save_image_revision(tx.session, image.cancel(image.updated_at))
        for _ in range(2):
            await tx.create_image(replace(original, id=uuid4(), client_message_id=uuid4()))
    listing = ListOwnImagePreparations(unit(owned), HASHER)
    result = await listing(owned.sender.credential, owned.conversation_id)
    assert len(result) == OWNED_IMAGE_LIMIT
    assert len({entry.preparation.id for entry in result}) == OWNED_IMAGE_LIMIT
    assert sum(entry.preparation.pending for entry in result) == len(("first", "second", "third"))
    keys = tuple((entry.preparation.created_at, entry.preparation.id.int) for entry in result)
    assert keys == tuple(sorted(keys, reverse=True))
    # A corrupt overcapacity set must fail closed rather than hide a pending root.
    async with owned.api.sessions.begin() as session:
        tx = SqlChatImageStartTransaction(session, owned.conversation_id, record_message_outcome)
        await authorize_conversation(tx, HASHER, owned.sender.credential, owned.conversation_id)
        await tx.create_image(replace(original, id=uuid4(), client_message_id=uuid4()))
    with pytest.raises(RuntimeError, match="capacity"):
        await listing(owned.sender.credential, owned.conversation_id)


async def test_ready_image_send_recovers_actual_attachment_fk(identity_engine: AsyncEngine) -> None:
    from studymate.domain.messaging import MessageContent
    from tests.integration.chat_images.test_display import prepared

    owned, image, _storage = await prepared(identity_engine)
    read = ReadOwnedImagePreparation(unit(owned), HASHER)
    before = await read(owned.sender.credential, owned.conversation_id, image.id)
    assert before.message_outcome is None
    confirmed = await owned.send()(
        replace(
            owned.command(),
            client_message_id=image.client_message_id,
            content=MessageContent(image_id=image.id),
        )
    )
    assert confirmed.message is not None
    recovered = await read(owned.sender.credential, owned.conversation_id, image.id)
    assert recovered.message_outcome is not None
    assert recovered.message_outcome.message_id == confirmed.message.id
    assert recovered.message_outcome.message_image_id == image.id
    listed = await ListOwnImagePreparations(unit(owned), HASHER)(
        owned.sender.credential, owned.conversation_id
    )
    assert listed == (recovered,)


async def test_legacy_text_logical_confirmation_does_not_claim_an_image_attachment(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.domain.chat_images import ChatImagePreparation
    from studymate.domain.media import PhotoContentType, PhotoSource

    owned = await chat(identity_engine)
    command = owned.command()
    confirmed = await owned.send()(command)
    assert confirmed.message is not None
    # Retained legacy coexistence fixture: current intake disallows repurposing a
    # resolved logical send, so use actual authorized source adapters explicitly.
    async with owned.api.sessions.begin() as session:
        tx = SqlChatImageStartTransaction(session, owned.conversation_id, record_message_outcome)
        await authorize_conversation(tx, HASHER, owned.sender.credential, owned.conversation_id)
        now = await tx.now()
        source = ChatImagePreparation(
            uuid4(),
            owned.sender.id,
            owned.conversation_id,
            command.client_message_id,
            PhotoSource(100, b"p" * 32, PhotoContentType.PNG),
            now,
            now + timedelta(minutes=15),
            now + timedelta(hours=1),
            now,
        )
        await tx.create_image(source)
    recovered = await ReadOwnedImagePreparation(unit(owned), HASHER)(
        owned.sender.credential, owned.conversation_id, source.id
    )
    assert recovered.message_outcome is not None
    assert recovered.message_outcome.outcome == MessageOutcome.CONFIRMED
    assert recovered.message_outcome.message_id == confirmed.message.id
    assert recovered.message_outcome.message_image_id is None
