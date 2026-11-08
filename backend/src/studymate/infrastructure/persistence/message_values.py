from uuid import UUID

from sqlalchemy import Nullable, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.messaging import ConfirmedMessage, MessageContent, MessageOperation
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.persistence.message_models import (
    MessageOperationRecord,
    MessageRecord,
)


async def read_message_operation(
    session: AsyncSession, operation_id: UUID, author_id: UUID
) -> MessageOperation | None:
    row = (
        await session.execute(
            select(MessageOperationRecord, Nullable(MessageRecord))
            .outerjoin(MessageRecord, MessageRecord.id == MessageOperationRecord.message_id)
            .where(
                MessageOperationRecord.id == operation_id,
                MessageOperationRecord.author_id == author_id,
            )
        )
    ).one_or_none()
    if row is None:
        return None
    root, message = row
    pair = AccountPair(root.low_id, root.high_id)
    if (root.state == "confirmed") != (message is not None):
        raise RuntimeError("Terminal message projection lacks its actual confirmed source")
    return MessageOperation(
        root.id,
        root.conversation_id,
        pair,
        root.author_id,
        root.client_message_id,
        ConfirmedMessage(
            message.id,
            root.id,
            root.conversation_id,
            pair,
            root.author_id,
            root.client_message_id,
            message.sequence,
            MessageContent(message.text, message.image_id),
            message.sent_at,
        )
        if message is not None
        else None,
        root.cancelled_at,
    )
