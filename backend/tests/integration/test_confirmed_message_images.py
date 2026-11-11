from dataclasses import replace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.chat_images.worker import ChatImageProcessingStep, ProcessNextChatImage
from studymate.application.messaging.ports import MessageImageUnavailableError
from studymate.domain.media import MediaObjectKind
from studymate.domain.messaging import MessageContent
from studymate.infrastructure.chat_images.models import ChatImageRecord, ChatImageRevisionRecord
from studymate.infrastructure.chat_images.worker import SqlChatImageWorkerUnitOfWork
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.message_models import MessageRecord
from tests.image_fixture import encoded
from tests.integration.media_fixture import Storage
from tests.integration.test_chat_image_worker import queued

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("caption", [None, "Preserved private image caption"])
async def test_only_the_exact_owned_ready_rendition_becomes_one_confirmed_message(
    identity_engine: AsyncEngine, caption: str | None
) -> None:
    data = encoded()
    owned, image = await queued(identity_engine, data)
    storage, processor = Storage(data), BoundedImageProcessor()
    try:
        assert (
            await ProcessNextChatImage(
                SqlChatImageWorkerUnitOfWork(owned.api.sessions), storage, processor
            )()
            == ChatImageProcessingStep.READY
        )
    finally:
        await processor.close()
    command = replace(
        owned.command(),
        client_message_id=image.client_message_id,
        content=MessageContent(text=caption, image_id=image.id),
    )
    confirmed = await owned.send()(command)
    assert confirmed.message is not None
    assert confirmed.message.content == command.content
    assert confirmed.message.sequence == 1
    assert await owned.send()(command) == confirmed
    assert (
        await owned.read()(owned.sender.credential, owned.conversation_id, image.client_message_id)
        == confirmed
    )
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        ready = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        message = await session.get(MessageRecord, confirmed.message.id)
        assert ready is not None
        assert message is not None
        assert message.image_id == image.id
        assert message.image_version == ready.version
        assert message.image_attempt_id == ready.attempt_id
        assert message.image_state == "ready"
        assert message.text == caption
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 1
    assert any(reference.kind == MediaObjectKind.DISPLAY for reference in storage.retained)


@pytest.mark.parametrize("attempt", ["not_ready", "wrong_client", "text_repurpose", "wrong_owner"])
async def test_unready_or_unrelated_image_source_cannot_create_a_message(
    identity_engine: AsyncEngine, attempt: str
) -> None:
    owned, image = await queued(identity_engine, encoded())
    command = replace(
        owned.command(),
        client_message_id=image.client_message_id,
        content=MessageContent(image_id=image.id),
    )
    if attempt == "wrong_client":
        command = replace(command, client_message_id=owned.command().client_message_id)
    elif attempt == "text_repurpose":
        command = replace(
            command, content=MessageContent("Different source needs a new resolved intent")
        )
    elif attempt == "wrong_owner":
        command = replace(command, credential=owned.recipient.credential)
    with pytest.raises(MessageImageUnavailableError):
        await owned.send()(command)
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0
