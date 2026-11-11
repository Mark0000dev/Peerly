"""Exact message cancellation/preparation cleanup under the caller's scoped locks."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.messaging import MessageOperation
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.revisions import image_value, save_image_revision


async def cancel_prepared_image(session: AsyncSession, operation: MessageOperation) -> None:
    """Caller is the actual scoped MessageTransaction under participant/conversation locks."""
    if operation.cancelled_at is None:
        raise ValueError("Only a real cancelled message operation can cancel preparation")
    root, revision = ChatImageRecord, ChatImageRevisionRecord
    row = (
        await session.execute(
            select(root, revision)
            .join(
                revision,
                (revision.image_id == root.id) & (revision.version == root.current_version),
            )
            .where(
                root.account_id == operation.author_id,
                root.conversation_id == operation.conversation_id,
                root.client_message_id == operation.client_message_id,
                root.low_id == operation.pair.low,
                root.high_id == operation.pair.high,
            )
            .with_for_update(of=root)
        )
    ).one_or_none()
    if row is None:
        return
    current = image_value(*row)
    cancelled = current.cancel(operation.cancelled_at)
    if cancelled is current:
        return
    if current.attempt_id is not None:
        attempt = (
            await session.scalars(
                select(ChatImageAttemptRecord)
                .where(
                    ChatImageAttemptRecord.id == current.attempt_id,
                    ChatImageAttemptRecord.image_id == current.id,
                )
                .with_for_update()
            )
        ).one()
        if attempt.outcome == "processing":
            attempt.outcome = "interrupted"
            attempt.finished_at = cancelled.updated_at
            await session.flush()
    await save_image_revision(session, cancelled)
