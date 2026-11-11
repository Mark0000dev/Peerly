from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import OperatorCursorCodec, OperatorCursorScope
from studymate.application.operator.data import OperatorAccountDetail, OperatorAccountSummary
from studymate.application.operator.filters import OperatorAccountFilters
from studymate.application.operator.ports import (
    OperatorAccountPosition,
    OperatorAccountUnitOfWork,
    OperatorAccountWindow,
)
from studymate.domain.operator.audit import (
    OPERATOR_ACCOUNT_PAGE_SIZE,
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)


@dataclass(frozen=True, slots=True)
class OperatorAccountPage:
    accounts: tuple[OperatorAccountSummary, ...] = field(repr=False)
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class SearchOperatorAccounts:
    unit_of_work: OperatorAccountUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        filters: OperatorAccountFilters,
        cursor: str | None = None,
    ) -> OperatorAccountPage:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            now = await transaction.now()
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            position = (
                self.cursor_codec.decode_accounts(scope, digest, cursor, now)
                if cursor is not None
                else None
            )
            window = OperatorAccountWindow(
                position.as_of if position is not None else now, position
            )
            rows = await transaction.search_operator_accounts(filters, window)
            if len(rows) > OPERATOR_ACCOUNT_PAGE_SIZE + 1:
                raise RuntimeError("Operator account search exceeded its bounded page")
            previous = (
                (position.created_at, position.account_id.int) if position is not None else None
            )
            for row in rows:
                current = row.created_at, row.account_id.int
                if row.created_at > window.as_of or (previous is not None and current >= previous):
                    raise RuntimeError("Operator account search violates its fixed source ordering")
                previous = current
            visible = rows[:OPERATOR_ACCOUNT_PAGE_SIZE]
            next_cursor = (
                self.cursor_codec.encode_accounts(
                    scope,
                    digest,
                    OperatorAccountPosition(
                        window.as_of, visible[-1].created_at, visible[-1].account_id
                    ),
                )
                if len(rows) > OPERATOR_ACCOUNT_PAGE_SIZE
                else None
            )
            audit = OperatorAudit(
                uuid4(),
                principal.access,
                OperatorAction.SEARCH_ACCOUNTS,
                None,
                tuple(
                    OperatorResourceRef(OperatorResourceKind.ACCOUNT, row.account_id)
                    for row in visible
                ),
                await transaction.now(),
                OperatorAuditOutcome.SEARCH,
                digest,
            )
            await transaction.save_operator_audit(audit)
            await finish_operator(transaction, principal)
            return OperatorAccountPage(visible, next_cursor)


@dataclass(frozen=True, slots=True)
class ReadOperatorAccount:
    unit_of_work: OperatorAccountUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, account_id: UUID
    ) -> OperatorAccountDetail | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            account = await transaction.operator_account(account_id)
            if account is not None and account.account.account_id != account_id:
                raise RuntimeError("Operator account projection belongs to another target")
            resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_ACCOUNT,
                    resource,
                    (resource,) if account is not None else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ
                    if account is not None
                    else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return account
