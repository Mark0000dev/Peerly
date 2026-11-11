from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.domain.requests.states import ConnectionRequest
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.message_reads import (
    ReadPositionRecorder,
    SqlReadPositionTransaction,
)
from studymate.infrastructure.persistence.messaging import MessageOutcomeRecorder
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.requests.reads import read_request


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlConversationDetailsTransaction(SqlReadPositionTransaction):
    async def accepted_request(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConnectionRequest | None:
        self.check_scope(actor_id, conversation_id)
        record = self.authority.conversation
        if record is None:
            raise RuntimeError("Conversation context lacks its actual locked source")
        return await read_request(self.session, record.request_id, record.accepted_request_version)

    async def unread_messages(
        self, actor_id: UUID, conversation_id: UUID, through_sequence: int
    ) -> int:
        self.check_scope(actor_id, conversation_id)
        if through_sequence < 0:
            raise RuntimeError("Unread range cannot start before its actual source")
        result = await self.session.scalar(
            select(func.count())
            .select_from(MessageRecord)
            .where(
                MessageRecord.conversation_id == conversation_id,
                MessageRecord.author_id != actor_id,
                MessageRecord.sequence > through_sequence,
            )
        )
        if result is None:
            raise RuntimeError("Unread count projection returned no actual aggregate")
        return result


@dataclass(frozen=True, slots=True)
class SqlConversationDetailsUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    message_recorder: MessageOutcomeRecorder
    read_recorder: ReadPositionRecorder

    @asynccontextmanager
    async def transaction(
        self, conversation_id: UUID
    ) -> AsyncIterator[SqlConversationDetailsTransaction]:
        async with open_transaction(self.sessions, read_only=True) as session:
            yield SqlConversationDetailsTransaction(
                session,
                conversation_id,
                self.message_recorder,
                read_recorder=self.read_recorder,
                shared_identity_locks=True,
            )
