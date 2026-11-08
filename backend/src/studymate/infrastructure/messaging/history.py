from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.messaging.history_ports import (
    MESSAGE_HISTORY_PAGE_SIZE,
    MessageHistoryWindow,
)
from studymate.domain.messaging import ConfirmedMessage, MessageContent
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.messaging import (
    MessageOutcomeRecorder,
    SqlMessageTransaction,
)
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlMessageHistoryTransaction(SqlMessageTransaction):
    async def history_messages(
        self, actor_id: UUID, conversation_id: UUID, window: MessageHistoryWindow
    ) -> tuple[ConfirmedMessage, ...]:
        self.check_actor(actor_id)
        conversation = self.authority.conversation
        if (
            conversation is None
            or conversation.id != conversation_id
            or conversation_id != self.conversation_id
        ):
            raise RuntimeError("History read lacks its accepted conversation scope")
        statement = (
            select(MessageRecord)
            .join(ConversationRecord, ConversationRecord.id == MessageRecord.conversation_id)
            .where(
                MessageRecord.conversation_id == conversation_id,
                or_(ConversationRecord.low_id == actor_id, ConversationRecord.high_id == actor_id),
                MessageRecord.sequence <= window.anchor_sequence,
            )
        )
        if window.before_sequence is not None:
            statement = statement.where(MessageRecord.sequence < window.before_sequence)
        records = tuple(
            await self.session.scalars(
                statement.order_by(MessageRecord.sequence.desc()).limit(
                    MESSAGE_HISTORY_PAGE_SIZE + 1
                )
            )
        )
        return tuple(
            ConfirmedMessage(
                record.id,
                record.operation_id,
                record.conversation_id,
                AccountPair(record.low_id, record.high_id),
                record.author_id,
                record.client_message_id,
                record.sequence,
                MessageContent(record.text, record.image_id),
                record.sent_at,
            )
            for record in records
        )


@dataclass(frozen=True, slots=True)
class SqlMessageHistoryUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: MessageOutcomeRecorder

    @asynccontextmanager
    async def transaction(
        self, conversation_id: UUID
    ) -> AsyncIterator[SqlMessageHistoryTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlMessageHistoryTransaction(session, conversation_id, self.recorder)
