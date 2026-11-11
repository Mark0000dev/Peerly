"""Audited full retained help selections, bounded by actual account/version sources."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.help_history_ports import (
    OperatorHelpHistoryCursorCodec,
    OperatorHelpHistoryPosition,
    OperatorHelpHistoryUnitOfWork,
    OperatorHelpHistoryWindow,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.help_history import (
    OPERATOR_HELP_HISTORY_PAGE_SIZE,
    OperatorHelpHistoryRevision,
)


@dataclass(frozen=True, slots=True)
class OperatorHelpHistoryPage:
    account_id: UUID
    revisions: tuple[OperatorHelpHistoryRevision, ...] = field(repr=False)
    next_cursor: str | None
    anchor_version: int


@dataclass(frozen=True, slots=True)
class ReadOperatorHelpHistory:
    unit_of_work: OperatorHelpHistoryUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorHelpHistoryCursorCodec

    async def __call__(
        self, credential: SessionCredential, account_id: UUID, cursor: str | None = None
    ) -> OperatorHelpHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            head = await transaction.help_history_head(account_id)
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
                raise RuntimeError("Help history head belongs to another actual account")
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_history(scope, account_id, cursor)
                if cursor is not None
                else None
            )
            if position is not None and position.anchor_version > head.latest_version:
                raise InvalidOperatorCursorError
            anchor = position.anchor_version if position is not None else head.latest_version
            window = OperatorHelpHistoryWindow(
                anchor, position.before_version if position is not None else None
            )
            rows = await transaction.help_history_revisions(account_id, window)
            if len(rows) > OPERATOR_HELP_HISTORY_PAGE_SIZE + 1:
                raise RuntimeError("Help history exceeded its bounded source page")
            previous = window.before_version if window.before_version is not None else anchor + 1
            for row in rows:
                if row.account_id != account_id or row.version > anchor or row.version >= previous:
                    raise RuntimeError(
                        "Help history source violates actual owner or version ordering"
                    )
                previous = row.version
                previous_slot = -1
                for selection in row.selections:
                    if selection.slot <= previous_slot:
                        raise RuntimeError("Help history selections violate retained slot ordering")
                    previous_slot = selection.slot
            visible = rows[:OPERATOR_HELP_HISTORY_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_history(
                    scope, account_id, OperatorHelpHistoryPosition(anchor, visible[-1].version)
                )
                if len(rows) > OPERATOR_HELP_HISTORY_PAGE_SIZE
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
            return OperatorHelpHistoryPage(account_id, visible, continuation, anchor)
