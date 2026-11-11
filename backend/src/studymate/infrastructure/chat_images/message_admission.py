"""Resolve one exact current owned Ready rendition inside the message transaction."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.messaging.ports import MessageImageUnavailableError
from studymate.domain.messaging import MessageContent
from studymate.infrastructure.chat_images.models import ChatImageRecord, ChatImageRevisionRecord


@dataclass(frozen=True, slots=True)
class ReadyMessageImageSource:
    image_id: UUID
    version: int
    attempt_id: UUID


async def admit_message_image(
    session: AsyncSession,
    author_id: UUID,
    conversation_id: UUID,
    client_message_id: UUID,
    content: MessageContent,
) -> ReadyMessageImageSource | None:
    root, revision = ChatImageRecord, ChatImageRevisionRecord
    row = (
        await session.execute(
            select(root.id, revision.version, revision.attempt_id, revision.state)
            .join(
                revision,
                (revision.image_id == root.id) & (revision.version == root.current_version),
            )
            .where(
                root.account_id == author_id,
                root.conversation_id == conversation_id,
                root.client_message_id == client_message_id,
            )
            .with_for_update(of=root)
        )
    ).one_or_none()
    if content.image_id is None:
        if row is not None:
            # A source-bound logical send cannot be silently repurposed as text.
            raise MessageImageUnavailableError
        return None
    if row is None or row.id != content.image_id or row.state != "ready" or row.attempt_id is None:
        raise MessageImageUnavailableError
    return ReadyMessageImageSource(row.id, row.version, row.attempt_id)
