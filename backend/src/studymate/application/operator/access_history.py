"""Audited retained permission provenance, bounded by actual account/version sources."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.access_history_ports import (
    OperatorAccessHistoryCursorCodec,
    OperatorAccessHistoryPosition,
    OperatorAccessHistoryUnitOfWork,
    OperatorAccessHistoryWindow,
)
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.operator.access_history import (
    OPERATOR_ACCESS_HISTORY_PAGE_SIZE,
    OperatorAccessHistoryRevision,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)


@dataclass(frozen=True, slots=True)
class OperatorAccessHistoryPage:
    account_id: UUID
    revisions: tuple[OperatorAccessHistoryRevision, ...] = field(repr=False)
    next_cursor: str | None
    anchor_version: int


@dataclass(frozen=True, slots=True)
class ReadOperatorAccessHistory:
    unit_of_work: OperatorAccessHistoryUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorAccessHistoryCursorCodec

    async def __call__(
        self, credential: SessionCredential, account_id: UUID, cursor: str | None = None
    ) -> OperatorAccessHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            head = await transaction.access_history_head(account_id)
            if head is None:
                await transaction.save_operator_audit(
                    OperatorAudit(
                        uuid4(),
                        principal.access,
                        OperatorAction.READ_ACCOUNT,
                        resource,
                        (),
                        await transaction.now(),
                        OperatorAuditOutcome.NOT_FOUND,
                    )
                )
                await finish_operator(transaction, principal)
                return None
            if head.account_id != account_id:
                raise RuntimeError("Operator-access history head belongs to another actual account")
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_history(scope, account_id, cursor)
                if cursor is not None
                else None
            )
            if position is not None and position.anchor_version > head.latest_version:
                raise InvalidOperatorCursorError
            anchor = position.anchor_version if position is not None else head.latest_version
            window = OperatorAccessHistoryWindow(
                anchor, position.before_version if position is not None else None
            )
            rows = await transaction.access_history_revisions(account_id, window)
            if len(rows) > OPERATOR_ACCESS_HISTORY_PAGE_SIZE + 1:
                raise RuntimeError("Operator-access history exceeded its bounded source page")
            previous = window.before_version if window.before_version is not None else anchor + 1
            for row in rows:
                if row.account_id != account_id or row.version > anchor or row.version >= previous:
                    raise RuntimeError(
                        "Operator-access history source violates actual owner or version ordering"
                    )
                previous = row.version
            visible = rows[:OPERATOR_ACCESS_HISTORY_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_history(
                    scope, account_id, OperatorAccessHistoryPosition(anchor, visible[-1].version)
                )
                if len(rows) > OPERATOR_ACCESS_HISTORY_PAGE_SIZE
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
            return OperatorAccessHistoryPage(account_id, visible, continuation, anchor)
