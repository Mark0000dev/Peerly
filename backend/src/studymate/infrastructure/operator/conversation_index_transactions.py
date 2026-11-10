from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.conversation_index_ports import OperatorConversationPosition
from studymate.domain.operator.conversation_index import (
    OPERATOR_CONVERSATION_PAGE_SIZE,
    OperatorConversationSummary,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorConversationIndexTransaction(SqlOperatorTransaction):
    async def conversation_account(self, account_id: UUID) -> UUID | None:
        self.checked_access()
        return await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )

    async def indexed_conversations(
        self, account_id: UUID, position: OperatorConversationPosition | None
    ) -> tuple[OperatorConversationSummary, ...]:
        self.checked_access()
        statement = select(
            ConversationRecord.id,
            ConversationRecord.relationship_id,
            ConversationRecord.low_id,
            ConversationRecord.high_id,
            ConversationRecord.request_id,
            ConversationRecord.accepted_request_version,
        ).where(
            or_(ConversationRecord.low_id == account_id, ConversationRecord.high_id == account_id)
        )
        if position is not None:
            statement = statement.where(ConversationRecord.id < position.before_id)
        rows = (
            await self.session.execute(
                statement.order_by(ConversationRecord.id.desc()).limit(
                    OPERATOR_CONVERSATION_PAGE_SIZE + 1
                )
            )
        ).all()
        return tuple(OperatorConversationSummary(*row) for row in rows)


@dataclass(frozen=True, slots=True)
class SqlOperatorConversationIndexUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorConversationIndexTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorConversationIndexTransaction(session, self.recorder)
