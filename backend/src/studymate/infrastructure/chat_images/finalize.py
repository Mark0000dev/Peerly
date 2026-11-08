"""Finalize preparation under the same account/session/conversation lock order."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.chat_images.finalize import ChatImageFinalizeTransaction
from studymate.application.chat_images.start import ChatImageIntent
from studymate.application.idempotency import IntentKey
from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.origins import remember_image_queue_origin
from studymate.infrastructure.chat_images.revisions import image_value
from studymate.infrastructure.chat_images.start import SqlChatImageStartTransaction
from studymate.infrastructure.persistence.messaging import MessageOutcomeRecorder
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlChatImageFinalizeTransaction(SqlChatImageStartTransaction):
    async def image_finalize_intent(self, actor_id: UUID, key: IntentKey) -> ChatImageIntent | None:
        return await self._image_intent(actor_id, "finalize", key)

    async def owned_image(
        self, actor_id: UUID, conversation_id: UUID, image_id: UUID
    ) -> ChatImagePreparation | None:
        self.check_conversation(actor_id, conversation_id)
        root, revision = ChatImageRecord, ChatImageRevisionRecord
        row = (
            await self.session.execute(
                select(root, revision)
                .join(
                    revision,
                    (revision.image_id == root.id) & (revision.version == root.current_version),
                )
                .where(
                    root.account_id == actor_id,
                    root.conversation_id == conversation_id,
                    root.id == image_id,
                )
                .with_for_update(of=root)
            )
        ).one_or_none()
        return image_value(*row) if row is not None else None

    async def save_image(self, image: ChatImagePreparation) -> None:
        self.check_conversation(image.account_id, image.conversation_id)
        if image.state == ChatImageState.EXPIRED and image.attempt_id is not None:
            attempt = await self.session.get(ChatImageAttemptRecord, image.attempt_id)
            if attempt is None or attempt.image_id != image.id:
                raise RuntimeError("Finalization expiry lost its owned processing attempt")
            if attempt.outcome == "processing":
                attempt.outcome = "interrupted"
                attempt.finished_at = image.updated_at
                await self.session.flush()
        await self._save_revision(image)
        if image.state == ChatImageState.QUEUED:
            await remember_image_queue_origin(self.session, image)

    async def remember_image_finalize(
        self, actor_id: UUID, key: IntentKey, intent: ChatImageIntent, at: datetime
    ) -> None:
        await self._remember_image_intent(actor_id, "finalize", key, intent, at)


@dataclass(frozen=True, slots=True)
class SqlChatImageFinalizeUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: MessageOutcomeRecorder

    @asynccontextmanager
    async def transaction(
        self, conversation_id: UUID
    ) -> AsyncIterator[ChatImageFinalizeTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlChatImageFinalizeTransaction(session, conversation_id, self.recorder)
