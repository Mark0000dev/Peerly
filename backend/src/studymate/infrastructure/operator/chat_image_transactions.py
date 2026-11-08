"""Raw owned chat-image metadata; no object storage dependency or student-policy replay."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.chat_image_ports import (
    OperatorChatImageFilters,
    OperatorChatImageHistoryHead,
    OperatorChatImageHistoryWindow,
    OperatorChatImageUploadRootPosition,
)
from studymate.domain.chat_images import ChatImageFailure, ChatImageState
from studymate.domain.messaging import MessageOutcome
from studymate.domain.operator.chat_image_uploads import (
    MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS,
    OPERATOR_CHAT_IMAGE_PAGE_SIZE,
    OperatorChatImageAttempt,
    OperatorChatImageAttemptOutcome,
    OperatorChatImageMatchingOperation,
    OperatorChatImageUploadRevision,
    OperatorChatImageUploadRoot,
)
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.message_models import MessageOperationRecord
from studymate.infrastructure.persistence.transactions import open_transaction


def revision_value(row: ChatImageRevisionRecord) -> OperatorChatImageUploadRevision:
    return OperatorChatImageUploadRevision(
        row.image_id,
        row.account_id,
        row.conversation_id,
        row.client_message_id,
        row.version,
        ChatImageState(row.state),
        row.updated_at,
        row.attempt_id,
        OperatorChatImageAttemptOutcome(row.ready_attempt_outcome)
        if row.ready_attempt_outcome is not None
        else None,
        ChatImageFailure(row.failure) if row.failure is not None else None,
    )


def root_value(
    row: ChatImageRecord, revision: ChatImageRevisionRecord
) -> OperatorChatImageUploadRoot:
    return OperatorChatImageUploadRoot(
        row.id,
        row.account_id,
        row.conversation_id,
        row.low_id,
        row.high_id,
        row.client_message_id,
        row.current_version,
        row.source_size,
        row.source_digest,
        row.content_type,
        row.created_at,
        row.upload_expires_at,
        row.processing_expires_at,
        revision_value(revision),
    )


def attempt_value(row: ChatImageAttemptRecord) -> OperatorChatImageAttempt:
    return OperatorChatImageAttempt(
        row.id,
        row.image_id,
        row.number,
        row.started_at,
        row.lease_until,
        row.finished_at,
        row.next_attempt_at,
        OperatorChatImageAttemptOutcome(row.outcome),
        ChatImageFailure(row.failure) if row.failure is not None else None,
        row.display_width,
        row.display_height,
        row.display_size,
        row.display_digest,
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorChatImageTransaction(SqlOperatorTransaction):
    async def chat_image_account(self, account_id: UUID) -> UUID | None:
        self.checked_access()
        return await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )

    async def chat_image_roots(
        self,
        account_id: UUID,
        filters: OperatorChatImageFilters,
        position: OperatorChatImageUploadRootPosition | None,
    ) -> tuple[OperatorChatImageUploadRoot, ...]:
        self.checked_access()
        statement = (
            select(ChatImageRecord, ChatImageRevisionRecord)
            .join(
                ChatImageRevisionRecord,
                (ChatImageRevisionRecord.image_id == ChatImageRecord.id)
                & (ChatImageRevisionRecord.account_id == ChatImageRecord.account_id)
                & (ChatImageRevisionRecord.version == ChatImageRecord.current_version),
            )
            .where(ChatImageRecord.account_id == account_id)
        )
        if filters.conversation_id is not None:
            statement = statement.where(ChatImageRecord.conversation_id == filters.conversation_id)
        if filters.state is not None:
            statement = statement.where(ChatImageRevisionRecord.state == filters.state.value)
        if filters.created_from is not None:
            statement = statement.where(ChatImageRecord.created_at >= filters.created_from)
        if filters.created_before is not None:
            statement = statement.where(ChatImageRecord.created_at < filters.created_before)
        if position is not None:
            statement = statement.where(
                tuple_(ChatImageRecord.created_at, ChatImageRecord.id)
                <= tuple_(position.anchor_created_at, position.anchor_image_id),
                tuple_(ChatImageRecord.created_at, ChatImageRecord.id)
                < tuple_(position.before_created_at, position.before_image_id),
            )
        rows = await self.session.execute(
            statement.order_by(ChatImageRecord.created_at.desc(), ChatImageRecord.id.desc()).limit(
                OPERATOR_CHAT_IMAGE_PAGE_SIZE + 1
            )
        )
        return tuple(root_value(root, revision) for root, revision in rows)

    async def chat_image_history_head(
        self, account_id: UUID, image_id: UUID
    ) -> OperatorChatImageHistoryHead | None:
        roots = await self.chat_image_roots_for_id(account_id, image_id)
        if roots is None:
            return None
        latest = await self.session.scalar(
            select(func.max(ChatImageRevisionRecord.version)).where(
                ChatImageRevisionRecord.image_id == image_id,
                ChatImageRevisionRecord.account_id == account_id,
            )
        )
        if latest is None:
            raise RuntimeError("Retained chat image upload lost its committed revisions")
        return OperatorChatImageHistoryHead(roots, latest)

    async def chat_image_roots_for_id(
        self, account_id: UUID, image_id: UUID
    ) -> OperatorChatImageUploadRoot | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(ChatImageRecord, ChatImageRevisionRecord)
                .join(
                    ChatImageRevisionRecord,
                    (ChatImageRevisionRecord.image_id == ChatImageRecord.id)
                    & (ChatImageRevisionRecord.account_id == ChatImageRecord.account_id)
                    & (ChatImageRevisionRecord.version == ChatImageRecord.current_version),
                )
                .where(ChatImageRecord.account_id == account_id, ChatImageRecord.id == image_id)
            )
        ).one_or_none()
        return root_value(row[0], row[1]) if row is not None else None

    async def chat_image_history_revisions(
        self,
        account_id: UUID,
        image_id: UUID,
        window: OperatorChatImageHistoryWindow,
    ) -> tuple[OperatorChatImageUploadRevision, ...]:
        self.checked_access()
        statement = select(ChatImageRevisionRecord).where(
            ChatImageRevisionRecord.account_id == account_id,
            ChatImageRevisionRecord.image_id == image_id,
            ChatImageRevisionRecord.version <= window.anchor_version,
        )
        if window.before_version is not None:
            statement = statement.where(ChatImageRevisionRecord.version < window.before_version)
        rows = await self.session.scalars(
            statement.order_by(ChatImageRevisionRecord.version.desc()).limit(
                OPERATOR_CHAT_IMAGE_PAGE_SIZE + 1
            )
        )
        return tuple(revision_value(row) for row in rows)

    async def chat_image_attempts_current(
        self, account_id: UUID, image_id: UUID
    ) -> tuple[OperatorChatImageAttempt, ...]:
        self.checked_access()
        rows = await self.session.scalars(
            select(ChatImageAttemptRecord)
            .join(
                ChatImageRecord,
                ChatImageRecord.id == ChatImageAttemptRecord.image_id,
            )
            .where(ChatImageRecord.account_id == account_id, ChatImageRecord.id == image_id)
            .order_by(ChatImageAttemptRecord.number)
            .limit(MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS + 1)
        )
        return tuple(attempt_value(row) for row in rows)

    async def chat_image_matching_operation(
        self, account_id: UUID, image_id: UUID
    ) -> OperatorChatImageMatchingOperation | None:
        self.checked_access()
        row = await self.session.scalar(
            select(MessageOperationRecord)
            .join(
                ChatImageRecord,
                (ChatImageRecord.account_id == MessageOperationRecord.author_id)
                & (ChatImageRecord.conversation_id == MessageOperationRecord.conversation_id)
                & (ChatImageRecord.client_message_id == MessageOperationRecord.client_message_id),
            )
            .where(ChatImageRecord.id == image_id, ChatImageRecord.account_id == account_id)
        )
        return (
            OperatorChatImageMatchingOperation(
                row.id,
                row.author_id,
                row.conversation_id,
                row.client_message_id,
                MessageOutcome(row.state),
                row.message_id,
                row.cancelled_at,
            )
            if row is not None
            else None
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorChatImageUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorChatImageTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorChatImageTransaction(session, self.recorder)
