"""Actual retained chat image/attempt joins; main supplies canonical typed audit adapter."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.chat_media_ports import OperatorChatMediaAudit
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.chat_media import OperatorChatMediaRequest, OperatorChatMediaSource
from studymate.infrastructure.chat_images.models import ChatImageAttemptRecord, ChatImageRecord
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorChatMediaTransaction(SqlOperatorTransaction):
    async def chat_media_source(
        self, request: OperatorChatMediaRequest
    ) -> OperatorChatMediaSource | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(ChatImageRecord.account_id, ChatImageRecord.id, ChatImageAttemptRecord.id)
                .join(ChatImageAttemptRecord, ChatImageAttemptRecord.image_id == ChatImageRecord.id)
                .where(
                    ChatImageRecord.account_id == request.account_id,
                    ChatImageRecord.id == request.image_id,
                    ChatImageAttemptRecord.id == request.attempt_id,
                )
            )
        ).one_or_none()
        return OperatorChatMediaSource(*row) if row is not None else None

    async def save_chat_media_audit(self, inspection: OperatorChatMediaAudit) -> None:
        ref = OperatorResourceRef(OperatorResourceKind.CHAT_MEDIA, inspection.request.image_id)
        await self.save_operator_audit(
            OperatorAudit(
                inspection.id,
                inspection.access,
                OperatorAction.READ_CHAT_MEDIA,
                ref,
                (ref,) if inspection.outcome == OperatorAuditOutcome.READ else (),
                inspection.at,
                inspection.outcome,
                chat_media_request=inspection.request,
                actual_source_image_id=inspection.actual_source_image_id,
            )
        )


@dataclass(frozen=True, slots=True)
class SqlOperatorChatMediaUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorChatMediaTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorChatMediaTransaction(session, self.recorder)
