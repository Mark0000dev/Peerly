"""Bounded owner image recovery without source writes, expiry sweeps or activity warming."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Nullable, Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.chat_images.reads import (
    PENDING_IMAGE_LIMIT,
    TERMINAL_IMAGE_LIMIT,
    ImageMessageOutcome,
    ImagePreparationSource,
    ReadyImageInfo,
)
from studymate.domain.chat_images import ChatImageState
from studymate.domain.messaging import MessageOutcome
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.chat_images.finalize import SqlChatImageFinalizeTransaction
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.revisions import image_value
from studymate.infrastructure.chat_images.start import PENDING
from studymate.infrastructure.persistence.message_models import (
    MessageOperationRecord,
    MessageRecord,
)
from studymate.infrastructure.persistence.messaging import MessageOutcomeRecorder
from studymate.infrastructure.persistence.transactions import open_transaction


def source_value(
    root: ChatImageRecord,
    revision: ChatImageRevisionRecord,
    attempt: ChatImageAttemptRecord | None,
    operation: MessageOperationRecord | None,
    message_image_id: UUID | None = None,
) -> ImagePreparationSource:
    image = image_value(root, revision)
    ready = None
    if image.state == ChatImageState.READY:
        if (
            attempt is None
            or attempt.id != image.attempt_id
            or attempt.image_id != image.id
            or attempt.outcome != "ready"
            or attempt.display_width is None
            or attempt.display_height is None
            or attempt.display_size is None
        ):
            raise RuntimeError("Image recovery lost its actual owned ready attempt metadata")
        ready = ReadyImageInfo(
            attempt.id, attempt.display_width, attempt.display_height, attempt.display_size
        )
    outcome = None
    if operation is not None:
        outcome = ImageMessageOutcome(
            operation.id,
            AccountPair(operation.low_id, operation.high_id),
            operation.author_id,
            operation.conversation_id,
            operation.client_message_id,
            MessageOutcome(operation.state),
            operation.message_id,
            message_image_id,
        )
    return ImagePreparationSource(image, ready, outcome)


@dataclass(frozen=True, slots=True)
class SqlImageReadTransaction(SqlChatImageFinalizeTransaction):
    def sources_query(
        self, account_id: UUID, conversation_id: UUID
    ) -> Select[
        ChatImageRecord,
        ChatImageRevisionRecord,
        ChatImageAttemptRecord | None,
        MessageOperationRecord | None,
        UUID | None,
    ]:
        self.check_conversation(account_id, conversation_id)
        root, revision = ChatImageRecord, ChatImageRevisionRecord
        attempt, operation = ChatImageAttemptRecord, MessageOperationRecord
        return (
            select(root, revision, Nullable(attempt), Nullable(operation), MessageRecord.image_id)
            .join(
                revision,
                and_(revision.image_id == root.id, revision.version == root.current_version),
            )
            .outerjoin(
                attempt,
                and_(
                    attempt.image_id == root.id,
                    attempt.id == revision.attempt_id,
                    revision.state == "ready",
                ),
            )
            .outerjoin(
                operation,
                and_(
                    operation.author_id == root.account_id,
                    operation.conversation_id == root.conversation_id,
                    operation.client_message_id == root.client_message_id,
                ),
            )
            .outerjoin(
                MessageRecord,
                and_(
                    MessageRecord.id == operation.message_id,
                    MessageRecord.operation_id == operation.id,
                ),
            )
            .where(root.account_id == account_id, root.conversation_id == conversation_id)
        )

    async def image_source(
        self,
        account_id: UUID,
        conversation_id: UUID,
        image_id: UUID,
    ) -> ImagePreparationSource | None:
        row = (
            await self.session.execute(
                self.sources_query(account_id, conversation_id).where(
                    ChatImageRecord.id == image_id
                )
            )
        ).one_or_none()
        return source_value(*row) if row is not None else None

    async def image_sources(
        self,
        account_id: UUID,
        conversation_id: UUID,
    ) -> tuple[ImagePreparationSource, ...]:
        query = self.sources_query(account_id, conversation_id).order_by(
            ChatImageRecord.created_at.desc(), ChatImageRecord.id.desc()
        )
        pending = tuple(
            await self.session.execute(
                query.where(ChatImageRevisionRecord.state.in_(PENDING)).limit(
                    PENDING_IMAGE_LIMIT + 1
                )
            )
        )
        if len(pending) > PENDING_IMAGE_LIMIT:
            raise RuntimeError("Actual owned pending image capacity is inconsistent")
        terminal = tuple(
            await self.session.execute(
                query.where(ChatImageRevisionRecord.state.not_in(PENDING)).limit(
                    TERMINAL_IMAGE_LIMIT
                )
            )
        )
        sources = tuple(source_value(*row) for row in (*pending, *terminal))
        return tuple(
            sorted(
                sources,
                key=lambda source: (source.preparation.created_at, source.preparation.id.int),
                reverse=True,
            )
        )


@dataclass(frozen=True, slots=True)
class SqlImageReadUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: MessageOutcomeRecorder

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[SqlImageReadTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlImageReadTransaction(session, conversation_id, self.recorder)
