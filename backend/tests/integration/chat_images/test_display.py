"""Real READY/message FKs and final authorization, with controlled retained storage."""

import asyncio
from dataclasses import replace

import pytest
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.application.chat_images.display import ReadMessageImageDisplay, ReadOwnedImageDisplay
from studymate.application.chat_images.finalize import ChatImageUnavailableError
from studymate.application.chat_images.worker import ProcessNextChatImage
from studymate.application.discovery.profiles import ReadDiscoveryProfile
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.messaging.ports import ConversationUnavailableError
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.domain.chat_images import ChatImagePreparation
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.domain.messaging import MessageContent
from studymate.infrastructure.chat_images.display import SqlImageDisplayUnitOfWork
from studymate.infrastructure.chat_images.worker import SqlChatImageWorkerUnitOfWork
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.image_fixture import encoded
from tests.integration.lifecycle.test_deletion_transactions import command_for
from tests.integration.lifecycle.test_real_effects import deletion
from tests.integration.media_fixture import Storage
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import complete_existing_setup
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import actor
from tests.integration.test_chat_image_worker import queued
from tests.integration.test_message_commands import Chat

pytestmark = pytest.mark.integration


async def prepared(engine: AsyncEngine) -> tuple[Chat, ChatImagePreparation, Storage]:
    data = encoded()
    owned, image = await queued(engine, data)
    storage, processor = Storage(data), BoundedImageProcessor()
    try:
        await ProcessNextChatImage(
            SqlChatImageWorkerUnitOfWork(owned.api.sessions), storage, processor
        )()
    finally:
        await processor.close()
    return owned, image, storage


def unit(owned: Chat) -> SqlImageDisplayUnitOfWork:
    return SqlImageDisplayUnitOfWork(owned.api.sessions, record_message_outcome)


async def test_only_owned_ready_preview_and_actual_message_attachment_authorize_display(
    identity_engine: AsyncEngine,
) -> None:
    owned, image, storage = await prepared(identity_engine)
    preview = ReadOwnedImageDisplay(unit(owned), HASHER, storage)
    display = ReadMessageImageDisplay(unit(owned), HASHER, storage)
    ready = await preview(owned.sender.credential, owned.conversation_id, image.id)
    assert ready.data.startswith(b"\xff\xd8\xff")
    assert ready.content_type == "image/jpeg"
    with pytest.raises(ChatImageUnavailableError):
        await preview(owned.recipient.credential, owned.conversation_id, image.id)
    with pytest.raises(ChatImageUnavailableError):
        await display(owned.recipient.credential, owned.conversation_id, image.id)
    confirmed = await owned.send()(
        replace(
            owned.command(),
            client_message_id=image.client_message_id,
            content=MessageContent(image_id=image.id),
        )
    )
    assert confirmed.message is not None
    result = await display(owned.recipient.credential, owned.conversation_id, confirmed.message.id)
    assert result == ready
    stranger = await actor(identity_engine)
    await ready_setup(identity_engine, stranger.credential)
    await complete_existing_setup(identity_engine, stranger)
    with pytest.raises(ConversationUnavailableError):
        await display(stranger.credential, owned.conversation_id, confirmed.message.id)
    # Profile evidence authorizes only the separate block command, never display.
    profile = await ReadDiscoveryProfile(SqlDiscoveryProfileUnitOfWork(owned.api.sessions), HASHER)(
        owned.recipient.credential, owned.sender.id
    )
    # A block stops new sends, not access to the actual retained message.
    await ChangeOwnBlock(SqlBlockUnitOfWork(owned.api.sessions), HASHER, FINGERPRINTER)(
        ChangeBlockCommand(
            owned.recipient.credential,
            owned.sender.id,
            True,
            0,
            owned.command().intent_key,
            profile.access_context.id,
        )
    )
    assert (
        await display(owned.recipient.credential, owned.conversation_id, confirmed.message.id)
        == ready
    )
    await deletion(identity_engine)(await command_for(identity_engine, owned.sender))
    assert (
        await display(owned.recipient.credential, owned.conversation_id, confirmed.message.id)
        == ready
    )
    with pytest.raises(UnauthenticatedError):
        await preview(owned.sender.credential, owned.conversation_id, image.id)
    async with owned.api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owned.recipient.id)
            .values(banned_at=func.clock_timestamp())
        )
    with pytest.raises(StudentActionDeniedError):
        await display(owned.recipient.credential, owned.conversation_id, confirmed.message.id)


class PausedReader:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.references: list[MediaObjectRef] = []

    async def read(self, reference: MediaObjectRef) -> bytes:
        self.references.append(reference)
        assert reference.kind == MediaObjectKind.DISPLAY
        self.started.set()
        await self.release.wait()
        return await self.storage.read(reference)


@pytest.mark.parametrize("mutation", ["revoke", "ban", "delete"])
async def test_display_releases_sql_during_storage_and_rechecks_actual_actor(
    mutation: str, identity_engine: AsyncEngine
) -> None:
    owned, image, storage = await prepared(identity_engine)
    reader = PausedReader(storage)
    display = ReadOwnedImageDisplay(unit(owned), HASHER, reader)
    task = asyncio.create_task(display(owned.sender.credential, owned.conversation_id, image.id))
    try:
        await asyncio.wait_for(reader.started.wait(), timeout=5)
        assert isinstance(identity_engine.pool, AsyncAdaptedQueuePool)
        # This isolated fixture has no heartbeat/other concurrent pool clients.
        assert identity_engine.pool.checkedout() == 0
        async with owned.api.sessions.begin() as session:
            if mutation == "revoke":
                await session.execute(
                    update(SessionRecord)
                    .where(SessionRecord.account_id == owned.sender.id)
                    .values(revoked_at=func.clock_timestamp())
                )
            else:
                values = {
                    "banned_at" if mutation == "ban" else "deleted_at": func.clock_timestamp()
                }
                await session.execute(
                    update(AccountRecord)
                    .where(AccountRecord.id == owned.sender.id)
                    .values(**values)
                )
        reader.release.set()
        error = StudentActionDeniedError if mutation == "ban" else UnauthenticatedError
        with pytest.raises(error):
            await asyncio.wait_for(task, timeout=5)
    finally:
        reader.release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert len(reader.references) == 1
