"""Shared owned image value/revision persistence.

The caller owns actual account/conversation/image locks and authority checks.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.chat_images import ChatImageFailure, ChatImagePreparation, ChatImageState
from studymate.domain.media import PhotoContentType, PhotoSource
from studymate.infrastructure.chat_images.models import ChatImageRecord, ChatImageRevisionRecord


def image_value(root: ChatImageRecord, revision: ChatImageRevisionRecord) -> ChatImagePreparation:
    return ChatImagePreparation(
        root.id,
        root.account_id,
        root.conversation_id,
        root.client_message_id,
        PhotoSource(root.source_size, root.source_digest, PhotoContentType(root.content_type)),
        root.created_at,
        root.upload_expires_at,
        root.processing_expires_at,
        revision.updated_at,
        revision.version,
        ChatImageState(revision.state),
        revision.attempt_id,
        ChatImageFailure(revision.failure) if revision.failure is not None else None,
    )


async def save_image_revision(session: AsyncSession, image: ChatImagePreparation) -> None:
    root = await session.get(ChatImageRecord, image.id)
    if root is None or (root.account_id, root.conversation_id, root.client_message_id) != (
        image.account_id,
        image.conversation_id,
        image.client_message_id,
    ):
        raise RuntimeError("Image revision differs from its owned immutable source")
    session.add(
        ChatImageRevisionRecord(
            image_id=image.id,
            version=image.version,
            account_id=image.account_id,
            conversation_id=image.conversation_id,
            client_message_id=image.client_message_id,
            state=image.state.value,
            updated_at=image.updated_at,
            attempt_id=image.attempt_id,
            ready_attempt_outcome="ready" if image.state == ChatImageState.READY else None,
            failure=image.failure.value if image.failure is not None else None,
        )
    )
    await session.flush()
    root.current_version = image.version
    await session.flush()
