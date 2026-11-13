"""Audited retained email history: no authorization or verification mutations."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.email_history_ports import (
    EmailHistoryCursorCodec,
    EmailHistoryPosition,
    EmailHistoryUnitOfWork,
    EmailHistoryWindow,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.email_history import EMAIL_HISTORY_PAGE_SIZE, EmailHistoryChallenge


@dataclass(frozen=True, slots=True)
class OperatorEmailHistoryPage:
    account_id: UUID
    challenges: tuple[EmailHistoryChallenge, ...] = field(repr=False)
    next_cursor: str | None
    as_of: datetime


@dataclass(frozen=True, slots=True)
class ReadOperatorEmailHistory:
    unit_of_work: EmailHistoryUnitOfWork
    hasher: SessionHasher
    cursor_codec: EmailHistoryCursorCodec

    async def __call__(
        self, credential: SessionCredential, account_id: UUID, cursor: str | None = None
    ) -> OperatorEmailHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            exists = await transaction.email_history_account_exists(account_id)
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            now = await transaction.now()
            if not exists:
                await transaction.save_operator_audit(
                    OperatorAudit(
                        uuid4(),
                        principal.access,
                        OperatorAction.READ_ACCOUNT,
                        resource,
                        (),
                        now,
                        OperatorAuditOutcome.NOT_FOUND,
                    )
                )
                await finish_operator(transaction, principal)
                return None
            position = (
                self.cursor_codec.decode_history(scope, account_id, cursor, now)
                if cursor is not None
                else None
            )
            as_of = position.as_of if position is not None else now
            rows = await transaction.email_history_challenges(
                account_id, EmailHistoryWindow(as_of, position)
            )
            if len(rows) > EMAIL_HISTORY_PAGE_SIZE + 1:
                raise RuntimeError("Email history exceeded its bounded source page")
            previous = (
                (position.created_at, position.challenge_id) if position is not None else None
            )
            for row in rows:
                key = (row.created_at, row.id)
                if (
                    row.account_id != account_id
                    or row.created_at > as_of
                    or (previous is not None and key >= previous)
                ):
                    raise RuntimeError("Email history violates actual owner or source ordering")
                previous = key
            visible = rows[:EMAIL_HISTORY_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_history(
                    scope,
                    account_id,
                    EmailHistoryPosition(as_of, visible[-1].created_at, visible[-1].id),
                )
                if len(rows) > EMAIL_HISTORY_PAGE_SIZE
                else None
            )
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_ACCOUNT,
                    resource,
                    (resource,),
                    await transaction.now(),
                    OperatorAuditOutcome.READ,
                )
            )
            await finish_operator(transaction, principal)
            return OperatorEmailHistoryPage(account_id, visible, continuation, as_of)
