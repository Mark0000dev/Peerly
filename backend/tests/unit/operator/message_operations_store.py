from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from studymate.application.operator.message_operations_ports import OperatorMessageOperationPosition
from studymate.domain.messaging import MessageOutcome
from studymate.domain.operator.message_operations import (
    OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE,
    OperatorMessageOperation,
    OperatorOperationMessage,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store


def operation(
    number: int, *, confirmed: bool = False, author_id: UUID = TARGET
) -> OperatorMessageOperation:
    message = (
        OperatorOperationMessage(
            UUID(int=1000 + number), number, NOW, "  private retained text  ", None, None, None
        )
        if confirmed
        else None
    )
    return OperatorMessageOperation(
        UUID(int=number),
        UUID(int=500),
        TARGET,
        UUID(int=900),
        author_id,
        UUID(int=2000 + number),
        MessageOutcome.CONFIRMED if confirmed else MessageOutcome.CANCELLED,
        message.id if message else None,
        None if confirmed else NOW,
        NOW,
        message,
    )


class OperationsStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.operations = tuple(operation(n, confirmed=n % 2 == 0) for n in range(3, 0, -1))
        self.accounts = {TARGET}
        self.rows_override: tuple[OperatorMessageOperation, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["OperationsStore"]:
        async with Store.transaction(self):
            yield self

    async def operation_account(self, account_id: UUID) -> UUID | None:
        self.queried()
        return account_id if account_id in self.accounts else None

    async def terminal_operations(
        self, account_id: UUID, position: OperatorMessageOperationPosition | None, as_of: datetime
    ) -> tuple[OperatorMessageOperation, ...]:
        self.queried()
        if self.rows_override is not None:
            return self.rows_override
        return tuple(
            row
            for row in self.operations
            if row.author_id == account_id
            and row.terminal_at <= as_of
            and (
                position is None or (row.terminal_at, row.id) < (position.terminal_at, position.id)
            )
        )[: OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE + 1]

    async def terminal_operation(
        self, account_id: UUID, operation_id: UUID
    ) -> OperatorMessageOperation | None:
        self.queried()
        return next(
            (
                row
                for row in self.operations
                if row.author_id == account_id and row.id == operation_id
            ),
            None,
        )
