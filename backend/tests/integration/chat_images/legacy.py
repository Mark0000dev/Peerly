"""Retained pre-image-admission history, never a supported modern Send workflow."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select

from studymate.domain.chat_images import ChatImagePreparation
from studymate.domain.messaging import MessageOperation
from studymate.infrastructure.chat_images.models import ChatImageRecord
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.message_models import (
    MessageOperationRecord,
    MessageRecord,
)
from studymate.infrastructure.persistence.message_values import read_message_operation
from tests.integration.test_message_commands import Chat


async def seed_legacy_text_outcome(owned: Chat, image: ChatImagePreparation) -> MessageOperation:
    """An actual TEXT message may historically share a client ID without an attachment.

    Current Send correctly forbids repurposing an image-bound client ID. This fixture
    inserts the retained older shape with real FK ownership and sequence, and explicitly
    NULL image references. It grants no application permission and emits no invented
    historical canonical event. Original business records remain intact.
    """
    async with owned.api.sessions.begin() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        assert (root.account_id, root.conversation_id, root.client_message_id) == (
            image.account_id,
            owned.conversation_id,
            image.client_message_id,
        )
        conversation = await session.scalar(
            select(ConversationRecord)
            .where(ConversationRecord.id == image.conversation_id)
            .with_for_update()
        )
        assert conversation is not None
        assert image.account_id in (conversation.low_id, conversation.high_id)
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        operation_id, message_id = uuid4(), uuid4()
        session.add(
            MessageOperationRecord(
                id=operation_id,
                conversation_id=conversation.id,
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
                conversation_id=conversation.id,
                low_id=conversation.low_id,
                high_id=conversation.high_id,
                author_id=image.account_id,
                client_message_id=image.client_message_id,
                state="confirmed",
                sequence=conversation.next_message_sequence,
                text="Synthetic private message\n  preserved indentation",
                sent_at=now,
                image_id=None,
                image_version=None,
                image_attempt_id=None,
                image_state=None,
            )
        )
        conversation.next_message_sequence += 1
        await session.flush()
        result = await read_message_operation(session, operation_id, image.account_id)
        assert result is not None
        assert result.message is not None
        assert result.message.content.image_id is None
        return result
