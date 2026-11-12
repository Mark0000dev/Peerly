"""Audited terminal sends scoped to the actual author account, not inferred participation."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.message_operations_ports import (
    OperatorMessageOperationCursorCodec,
    OperatorMessageOperationPosition,
    OperatorMessageOperationsTransaction,
    OperatorMessageOperationsUnitOfWork,
)
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.message_operations import (
    OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE,
    OperatorMessageOperation,
)


@dataclass(frozen=True, slots=True)
class OperatorMessageOperationsPage:
    account_id: UUID
    operations: tuple[OperatorMessageOperation, ...] = field(repr=False)
    next_cursor: str | None


async def audit_operation_read(
    transaction: OperatorMessageOperationsTransaction,
    access: OperatorAccess,
    account_id: UUID,
    found: bool,
) -> None:
    ref = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
    await transaction.save_operator_audit(
        OperatorAudit(
            uuid4(),
            access,
            OperatorAction.READ_ACCOUNT,
            ref,
            (ref,) if found else (),
            await transaction.now(),
            OperatorAuditOutcome.READ if found else OperatorAuditOutcome.NOT_FOUND,
        )
    )


def validate_operations(
    rows: tuple[OperatorMessageOperation, ...],
    account_id: UUID,
    position: OperatorMessageOperationPosition | None,
) -> None:
    if len(rows) > OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE + 1:
        raise RuntimeError("Message operations exceeded their bounded page")
    previous = (position.terminal_at, position.id) if position is not None else None
    for row in rows:
        current = (row.terminal_at, row.id)
        if row.author_id != account_id or (previous is not None and current >= previous):
            raise RuntimeError("Message operations violated actual author or terminal ordering")
        previous = current


@dataclass(frozen=True, slots=True)
class ReadOperatorMessageOperations:
    unit_of_work: OperatorMessageOperationsUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorMessageOperationCursorCodec

    async def __call__(
        self, credential: SessionCredential, account_id: UUID, cursor: str | None = None
    ) -> OperatorMessageOperationsPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.operation_account(account_id)
            result = None
            if actual is not None:
                if actual != account_id:
                    raise RuntimeError("Message operations account differs from target")
                scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
                position = (
                    self.cursor_codec.decode_operations(scope, account_id, cursor)
                    if cursor is not None
                    else None
                )
                now = await transaction.now()
                if position is not None and position.as_of > now:
                    raise InvalidOperatorCursorError
                as_of = position.as_of if position is not None else now
                rows = await transaction.terminal_operations(account_id, position, as_of)
                validate_operations(rows, account_id, position)
                visible = rows[:OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE]
                continuation = (
                    self.cursor_codec.encode_operations(
                        scope,
                        account_id,
                        OperatorMessageOperationPosition(
                            visible[-1].terminal_at, visible[-1].id, as_of
                        ),
                    )
                    if len(rows) > OPERATOR_MESSAGE_OPERATIONS_PAGE_SIZE
                    else None
                )
                result = OperatorMessageOperationsPage(account_id, visible, continuation)
            await audit_operation_read(
                transaction, principal.access, account_id, result is not None
            )
            await finish_operator(transaction, principal)
            return result


@dataclass(frozen=True, slots=True)
class ReadOperatorMessageOperation:
    unit_of_work: OperatorMessageOperationsUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, account_id: UUID, operation_id: UUID
    ) -> OperatorMessageOperation | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.operation_account(account_id)
            if actual is not None and actual != account_id:
                raise RuntimeError("Message operations account differs from target")
            result = (
                await transaction.terminal_operation(account_id, operation_id)
                if actual is not None
                else None
            )
            if result is not None and (result.author_id != account_id or result.id != operation_id):
                raise RuntimeError("Message operation source differs from requested author or ID")
            await audit_operation_read(
                transaction, principal.access, account_id, actual is not None
            )
            await finish_operator(transaction, principal)
            return result
