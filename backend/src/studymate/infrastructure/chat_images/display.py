"""Display references come from an owned current READY root or an actual message FK."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.chat_images.display import ImageDisplaySource
from studymate.infrastructure.chat_images.finalize import SqlChatImageFinalizeTransaction
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.messaging import MessageOutcomeRecorder
from studymate.infrastructure.persistence.transactions import open_transaction


def display_source(
    root: ChatImageRecord,
    revision: ChatImageRevisionRecord,
    attempt: ChatImageAttemptRecord,
    message_id: UUID | None,
) -> ImageDisplaySource:
    if (
        revision.state != "ready"
        or attempt.outcome != "ready"
        or (revision.image_id, revision.attempt_id) != (root.id, attempt.id)
        or attempt.image_id != root.id
        or attempt.display_width is None
        or attempt.display_height is None
        or attempt.display_size is None
        or attempt.display_digest is None
    ):
        raise RuntimeError("Display source lost its actual owned successful rendition")
    return ImageDisplaySource(
        root.id,
        revision.version,
        attempt.id,
        root.account_id,
        root.conversation_id,
        root.client_message_id,
        message_id,
        attempt.display_width,
        attempt.display_height,
        attempt.display_size,
        attempt.display_digest,
    )


@dataclass(frozen=True, slots=True)
class SqlImageDisplayTransaction(SqlChatImageFinalizeTransaction):
    async def owned_display_source(
        self,
        actor_id: UUID,
        conversation_id: UUID,
        image_id: UUID,
    ) -> ImageDisplaySource | None:
        self.check_conversation(actor_id, conversation_id)
        root, revision, attempt = ChatImageRecord, ChatImageRevisionRecord, ChatImageAttemptRecord
        row = (
            await self.session.execute(
                select(root, revision, attempt)
                .join(
                    revision,
                    and_(revision.image_id == root.id, revision.version == root.current_version),
                )
                .join(attempt, and_(attempt.image_id == root.id, attempt.id == revision.attempt_id))
                .where(
                    root.id == image_id,
                    root.account_id == actor_id,
                    root.conversation_id == conversation_id,
                    revision.state == "ready",
                )
            )
        ).one_or_none()
        return display_source(*row, None) if row is not None else None

    async def message_display_source(
        self,
        actor_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
    ) -> ImageDisplaySource | None:
        self.check_conversation(actor_id, conversation_id)
        message, root = MessageRecord, ChatImageRecord
        revision, attempt = ChatImageRevisionRecord, ChatImageAttemptRecord
        row = (
            await self.session.execute(
                select(root, revision, attempt)
                .select_from(message)
                .join(
                    root,
                    and_(
                        root.id == message.image_id,
                        root.account_id == message.author_id,
                        root.conversation_id == message.conversation_id,
                        root.client_message_id == message.client_message_id,
                    ),
                )
                .join(
                    revision,
                    and_(
                        revision.image_id == message.image_id,
                        revision.version == message.image_version,
                        revision.state == message.image_state,
                        revision.attempt_id == message.image_attempt_id,
                    ),
                )
                .join(
                    attempt,
                    and_(
                        attempt.image_id == message.image_id, attempt.id == message.image_attempt_id
                    ),
                )
                .where(
                    message.id == message_id,
                    message.conversation_id == conversation_id,
                    message.image_state == "ready",
                )
            )
        ).one_or_none()
        # Deliberately ignore root.current_version: the message pins its immutable
        # exact READY revision and attempt, including after later preparation changes.
        return display_source(*row, message_id) if row is not None else None


@dataclass(frozen=True, slots=True)
class SqlImageDisplayUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: MessageOutcomeRecorder

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[SqlImageDisplayTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlImageDisplayTransaction(session, conversation_id, self.recorder)
