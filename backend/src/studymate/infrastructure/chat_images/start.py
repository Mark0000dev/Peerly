"""Image admission under the existing sorted participant-account/session locks."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.chat_images.start import ChatImageIntent, ChatImageStartTransaction
from studymate.application.idempotency import IntentKey
from studymate.application.media.uploads import UploadBudget
from studymate.domain.chat_images import ChatImagePreparation, ChatImageState
from studymate.infrastructure.chat_images.cleanup_models import ChatImageTransportCleanupRecord
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageIntentRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.revisions import image_value, save_image_revision
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.persistence.discovery_exposure import record_foreground_activity
from studymate.infrastructure.persistence.messaging import (
    MessageOutcomeRecorder,
    SqlMessageTransaction,
)
from studymate.infrastructure.persistence.transactions import open_transaction

PENDING = ("uploading", "queued", "processing")


@dataclass(frozen=True, slots=True)
class SqlChatImageStartTransaction(SqlMessageTransaction):
    def check_conversation(self, actor_id: UUID, conversation_id: UUID) -> None:
        self.check_actor(actor_id)
        source = self.authority.conversation
        if source is None or source.id != conversation_id:
            raise RuntimeError("Image admission lacks actual accepted-conversation authority")

    async def image_start_intent(self, actor_id: UUID, key: IntentKey) -> ChatImageIntent | None:
        return await self._image_intent(actor_id, "start", key)

    async def _image_intent(
        self, actor_id: UUID, operation: str, key: IntentKey
    ) -> ChatImageIntent | None:
        self.check_actor(actor_id)
        record = await self.session.get(ChatImageIntentRecord, (actor_id, operation, key.value))
        if record is None:
            return None
        root, revision = ChatImageRecord, ChatImageRevisionRecord
        row = (
            await self.session.execute(
                select(root, revision)
                .join(revision, revision.image_id == root.id)
                .where(
                    root.account_id == actor_id,
                    root.id == record.image_id,
                    revision.version == record.result_version,
                )
            )
        ).one_or_none()
        if row is None:
            raise RuntimeError("Image receipt lost its retained owned revision")
        return ChatImageIntent(record.fingerprint, image_value(*row))

    async def client_image(
        self, actor_id: UUID, conversation_id: UUID, client_message_id: UUID
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
                    root.client_message_id == client_message_id,
                )
                .with_for_update(of=root)
            )
        ).one_or_none()
        return image_value(*row) if row is not None else None

    async def _pending(self, actor_id: UUID) -> tuple[ChatImagePreparation, ...]:
        self.check_actor(actor_id)
        root, revision = ChatImageRecord, ChatImageRevisionRecord
        # Account lock precedes every image writer; lock roots in UUID order.
        rows = tuple(
            await self.session.execute(
                select(root, revision)
                .join(
                    revision,
                    (revision.image_id == root.id) & (revision.version == root.current_version),
                )
                .where(
                    root.account_id == actor_id,
                    revision.state.in_(PENDING),
                )
                .order_by(root.id)
                .with_for_update(of=root)
            )
        )
        return tuple(image_value(*row) for row in rows)

    async def expire_pending_images(self, actor_id: UUID, at: datetime) -> None:
        for image in await self._pending(actor_id):
            expired = image.expire(at)
            if expired is image:
                continue
            if image.attempt_id is not None:
                attempt = await self.session.get(ChatImageAttemptRecord, image.attempt_id)
                if attempt is None or attempt.image_id != image.id:
                    raise RuntimeError("Image expiry lost its actual processing attempt")
                if attempt.outcome == "processing":
                    attempt.outcome = "interrupted"
                    attempt.finished_at = at
                    await self.session.flush()
            await self._save_revision(expired)

    async def image_budget(self, actor_id: UUID, since: datetime) -> UploadBudget:
        self.check_actor(actor_id)
        used, first = (
            await self.session.execute(
                select(func.count(), func.min(ChatImageRecord.created_at)).where(
                    ChatImageRecord.account_id == actor_id,
                    ChatImageRecord.created_at > since,
                )
            )
        ).one()
        pending = await self._pending(actor_id)
        expiry = min(
            (
                image.upload_expires_at
                if image.state == ChatImageState.UPLOADING
                else image.processing_expires_at
                for image in pending
            ),
            default=None,
        )
        return UploadBudget(used, first, len(pending), expiry)

    async def create_image(self, image: ChatImagePreparation) -> None:
        self.check_conversation(image.account_id, image.conversation_id)
        conversation = self.authority.conversation
        if conversation is None:
            raise RuntimeError("Image source lost its authorized conversation")
        if image.version != 1 or image.state != ChatImageState.UPLOADING:
            raise RuntimeError("Image admission must create its initial uploading revision")
        self.session.add(
            ChatImageRecord(
                id=image.id,
                account_id=image.account_id,
                conversation_id=image.conversation_id,
                low_id=conversation.low_id,
                high_id=conversation.high_id,
                client_message_id=image.client_message_id,
                current_version=image.version,
                source_size=image.source.size,
                source_digest=image.source.sha256,
                content_type=image.source.content_type.value,
                created_at=image.created_at,
                upload_expires_at=image.upload_expires_at,
                processing_expires_at=image.processing_expires_at,
            )
        )
        await self.session.flush()
        await self._save_revision(image)
        self.session.add(
            ChatImageTransportCleanupRecord(
                image_id=image.id,
                attempts=0,
                next_attempt_at=image.upload_expires_at,
            )
        )
        await self.session.flush()

    async def _save_revision(self, image: ChatImagePreparation) -> None:
        self.check_actor(image.account_id)
        await save_image_revision(self.session, image)

    async def remember_image_start(
        self, actor_id: UUID, key: IntentKey, intent: ChatImageIntent, at: datetime
    ) -> None:
        await self._remember_image_intent(actor_id, "start", key, intent, at)

    async def _remember_image_intent(
        self, actor_id: UUID, operation: str, key: IntentKey, intent: ChatImageIntent, at: datetime
    ) -> None:
        image = intent.result
        self.check_conversation(actor_id, image.conversation_id)
        origin = current_origin()
        self.session.add(
            ChatImageIntentRecord(
                account_id=actor_id,
                operation=operation,
                key=key.value,
                fingerprint=intent.fingerprint,
                conversation_id=image.conversation_id,
                client_message_id=image.client_message_id,
                image_id=image.id,
                result_version=image.version,
                created_at=at,
                http_request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()
        await record_foreground_activity(self.session, actor_id, at)


@dataclass(frozen=True, slots=True)
class SqlChatImageStartUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: MessageOutcomeRecorder

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[ChatImageStartTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlChatImageStartTransaction(session, conversation_id, self.recorder)
