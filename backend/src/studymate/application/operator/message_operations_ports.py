from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.message_operations import OperatorMessageOperation
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorMessageOperationPosition:
    terminal_at: datetime
    id: UUID
    as_of: datetime

    def __post_init__(self) -> None:
        require_aware(self.terminal_at)
        require_aware(self.as_of)
        if self.terminal_at > self.as_of:
            raise ValueError("Message operation cursor is beyond its server cutoff")


class OperatorMessageOperationCursorCodec(Protocol):
    def encode_operations(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        position: OperatorMessageOperationPosition,
    ) -> str: ...
    def decode_operations(
        self, scope: OperatorCursorScope, account_id: UUID, token: str
    ) -> OperatorMessageOperationPosition: ...


class OperatorMessageOperationsTransaction(OperatorAuditTransaction, Protocol):
    async def operation_account(self, account_id: UUID) -> UUID | None: ...
    async def terminal_operations(
        self, account_id: UUID, position: OperatorMessageOperationPosition | None, as_of: datetime
    ) -> tuple[OperatorMessageOperation, ...]: ...
    async def terminal_operation(
        self, account_id: UUID, operation_id: UUID
    ) -> OperatorMessageOperation | None: ...


class OperatorMessageOperationsUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorMessageOperationsTransaction]: ...
