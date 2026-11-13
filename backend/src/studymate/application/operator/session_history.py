"""Audited retained session history: no authorization or verification mutations."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.session_history_ports import (
    SessionHistoryCursorCodec,
    SessionHistoryPosition,
    SessionHistoryUnitOfWork,
    SessionHistoryWindow,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.session_history import SESSION_HISTORY_PAGE_SIZE, SessionHistoryEntry


@dataclass(frozen=True, slots=True)
class OperatorSessionHistoryPage:
    account_id: UUID
    sessions: tuple[SessionHistoryEntry, ...] = field(repr=False)
    next_cursor: str | None
    as_of: datetime


@dataclass(frozen=True, slots=True)
class ReadOperatorSessionHistory:
    unit_of_work: SessionHistoryUnitOfWork
    hasher: SessionHasher
    cursor_codec: SessionHistoryCursorCodec

    async def __call__(
        self, credential: SessionCredential, account_id: UUID, cursor: str | None = None
    ) -> OperatorSessionHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            exists = await transaction.session_history_account_exists(account_id)
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
            rows = await transaction.session_history_sessions(
                account_id, SessionHistoryWindow(as_of, position)
            )
            if len(rows) > SESSION_HISTORY_PAGE_SIZE + 1:
                raise RuntimeError("Session history exceeded its bounded source page")
            previous = (position.issued_at, position.session_id) if position is not None else None
            for row in rows:
                key = (row.issued_at, row.id)
                if (
                    row.account_id != account_id
                    or row.issued_at > as_of
                    or (previous is not None and key >= previous)
                ):
                    raise RuntimeError("Session history violates actual owner or source ordering")
                previous = key
            visible = rows[:SESSION_HISTORY_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_history(
                    scope,
                    account_id,
                    SessionHistoryPosition(as_of, visible[-1].issued_at, visible[-1].id),
                )
                if len(rows) > SESSION_HISTORY_PAGE_SIZE
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
            return OperatorSessionHistoryPage(account_id, visible, continuation, as_of)
