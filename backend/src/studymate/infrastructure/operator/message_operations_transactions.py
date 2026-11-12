"""Terminal source reads with author filtering before payload retrieval."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.message_operations_ports import OperatorMessageOperationPosition
from studymate.domain.messaging import MessageOutcome
from studymate.domain.operator.message_operations import (
    OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE,
    OperatorMessageOperation,
    OperatorOperationMessage,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.message_models import (
    MessageOperationRecord,
    MessageRecord,
)
from studymate.infrastructure.persistence.transactions import open_transaction


def operation_value(
    row: MessageOperationRecord, message: MessageRecord | None
) -> OperatorMessageOperation:
    content = None
    if message is not None:
        if (
            message.operation_id != row.id
            or message.id != row.message_id
            or message.author_id != row.author_id
            or message.conversation_id != row.conversation_id
        ):
            raise RuntimeError("Message operation actual content source mismatch")
        content = OperatorOperationMessage(
            message.id,
            message.sequence,
            message.sent_at,
            message.text,
            message.image_id,
            message.image_version,
            message.image_attempt_id,
        )
    terminal_at = message.sent_at if message is not None else row.cancelled_at
    if terminal_at is None:
        raise RuntimeError("Message operation is missing its terminal source time")
    return OperatorMessageOperation(
        row.id,
        row.conversation_id,
        row.low_id,
        row.high_id,
        row.author_id,
        row.client_message_id,
        MessageOutcome(row.state),
        row.message_id,
        row.cancelled_at,
        terminal_at,
        content,
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorMessageOperationsTransaction(SqlOperatorTransaction):
    async def operation_account(self, account_id: UUID) -> UUID | None:
        self.checked_access()
        return await self.session.scalar(
            select(AccountRecord.id).where(AccountRecord.id == account_id)
        )

    async def terminal_operations(
        self, account_id: UUID, position: OperatorMessageOperationPosition | None, as_of: datetime
    ) -> tuple[OperatorMessageOperation, ...]:
        self.checked_access()
        op, msg = MessageOperationRecord, MessageRecord
        terminal = func.coalesce(msg.sent_at, op.cancelled_at)
        statement = (
            select(op, msg)
            .outerjoin(msg, and_(msg.id == op.message_id, msg.operation_id == op.id))
            .where(
                terminal <= as_of,
                op.author_id == account_id,
                op.state.in_(("confirmed", "cancelled")),
            )
        )
        if position is not None:
            statement = statement.where(
                tuple_(terminal, op.id) < tuple_(position.terminal_at, position.id)
            )
        rows = await self.session.execute(
            statement.order_by(terminal.desc(), op.id.desc()).limit(
                OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE + 1
            )
        )
        return tuple(operation_value(operation, message) for operation, message in rows)

    async def terminal_operation(
        self, account_id: UUID, operation_id: UUID
    ) -> OperatorMessageOperation | None:
        self.checked_access()
        op, msg = MessageOperationRecord, MessageRecord
        row = (
            await self.session.execute(
                select(op, msg)
                .outerjoin(msg, and_(msg.id == op.message_id, msg.operation_id == op.id))
                .where(
                    op.id == operation_id,
                    op.author_id == account_id,
                    op.state.in_(("confirmed", "cancelled")),
                )
            )
        ).one_or_none()
        return operation_value(*row) if row is not None else None


@dataclass(frozen=True, slots=True)
class SqlOperatorMessageOperationsUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorMessageOperationsTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorMessageOperationsTransaction(session, self.recorder)
