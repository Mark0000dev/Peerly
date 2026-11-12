"""Audited full retained visibility revisions, bounded by actual account/version sources."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.visibility_history_ports import (
    OperatorVisibilityHistoryCursorCodec,
    OperatorVisibilityHistoryPosition,
    OperatorVisibilityHistoryUnitOfWork,
    OperatorVisibilityHistoryWindow,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.visibility_history import (
    OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE,
    OperatorVisibilityHistoryRevision,
)


@dataclass(frozen=True, slots=True)
class OperatorVisibilityHistoryPage:
    account_id: UUID
    current: OperatorVisibilityHistoryRevision | None
    revisions: tuple[OperatorVisibilityHistoryRevision, ...] = field(repr=False)
    next_cursor: str | None
    anchor_version: int


@dataclass(frozen=True, slots=True)
class ReadOperatorVisibilityHistory:
    unit_of_work: OperatorVisibilityHistoryUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorVisibilityHistoryCursorCodec

    async def __call__(
        self, credential: SessionCredential, account_id: UUID, cursor: str | None = None
    ) -> OperatorVisibilityHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            head = await transaction.visibility_history_head(account_id)
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
                raise RuntimeError("Visibility history head belongs to another actual account")
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_history(scope, account_id, cursor)
                if cursor is not None
                else None
            )
            if position is not None and position.anchor_version > head.latest_version:
                raise InvalidOperatorCursorError
            anchor = position.anchor_version if position is not None else head.latest_version
            window = OperatorVisibilityHistoryWindow(
                anchor, position.before_version if position is not None else None
            )
            rows = await transaction.visibility_history_revisions(account_id, window)
            if len(rows) > OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE + 1:
                raise RuntimeError("Visibility history exceeded its bounded source page")
            previous = window.before_version if window.before_version is not None else anchor + 1
            for row in rows:
                if row.account_id != account_id or row.version > anchor or row.version >= previous:
                    raise RuntimeError(
                        "Visibility history source violates actual owner or version ordering"
                    )
                previous = row.version
            visible = rows[:OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_history(
                    scope,
                    account_id,
                    OperatorVisibilityHistoryPosition(anchor, visible[-1].version),
                )
                if len(rows) > OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE
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
            return OperatorVisibilityHistoryPage(
                account_id, head.current, visible, continuation, anchor
            )
