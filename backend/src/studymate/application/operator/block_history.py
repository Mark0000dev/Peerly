from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.block_history_ports import (
    OperatorBlockHistoryCursorCodec,
    OperatorBlockHistoryPosition,
    OperatorBlockHistoryUnitOfWork,
    OperatorBlockHistoryWindow,
)
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.block_history import (
    OPERATOR_BLOCK_HISTORY_PAGE_SIZE,
    OperatorBlockHistoryAnchors,
    OperatorBlockHistoryHead,
)
from studymate.domain.relationships import AccountPair, BlockRevision


@dataclass(frozen=True, slots=True)
class OperatorBlockHistoryPage:
    account_id: UUID
    relationship_id: UUID
    pair: AccountPair
    current_heads: tuple[BlockRevision, ...] = field(repr=False)
    revisions: tuple[BlockRevision, ...] = field(repr=False)
    anchors: OperatorBlockHistoryAnchors
    next_cursor: str | None


def validate_block_history(
    rows: tuple[BlockRevision, ...],
    head: OperatorBlockHistoryHead,
    window: OperatorBlockHistoryWindow,
) -> None:
    if len(rows) > OPERATOR_BLOCK_HISTORY_PAGE_SIZE + 1:
        raise RuntimeError("Block history source exceeded its bounded page")
    previous = (
        (window.before.changed_at, window.before.blocker_id, window.before.version)
        if window.before is not None
        else None
    )
    for row in rows:
        current = row.changed_at, row.blocker_id, row.version
        if (
            row.relationship_id != head.relationship_id
            or row.pair != head.pair
            or row.version > window.anchors.for_blocker(head.pair, row.blocker_id)
            or (previous is not None and current >= previous)
        ):
            raise RuntimeError(
                "Block history source violates actual pair, directional anchor or ordering"
            )
        previous = current


@dataclass(frozen=True, slots=True)
class ReadOperatorBlockHistory:
    unit_of_work: OperatorBlockHistoryUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorBlockHistoryCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        relationship_id: UUID,
        cursor: str | None = None,
    ) -> OperatorBlockHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            account = await transaction.block_history_account(account_id)
            if account is not None and account != account_id:
                raise RuntimeError("Block history account source differs from requested container")
            head = (
                await transaction.block_history_head(account_id, relationship_id)
                if account is not None
                else None
            )
            result = None
            if head is not None:
                if head.relationship_id != relationship_id or account_id not in (
                    head.pair.low,
                    head.pair.high,
                ):
                    raise RuntimeError("Block history pair source differs from requested container")
                scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
                position = (
                    self.cursor_codec.decode_history(
                        scope, account_id, relationship_id, head.pair, cursor
                    )
                    if cursor is not None
                    else None
                )
                anchors = position.anchors if position is not None else head.anchors
                if (
                    anchors.low_version > head.anchors.low_version
                    or anchors.high_version > head.anchors.high_version
                ):
                    raise InvalidOperatorCursorError
                window = OperatorBlockHistoryWindow(anchors, position)
                rows = await transaction.block_history_revisions(head, window)
                validate_block_history(rows, head, window)
                visible = rows[:OPERATOR_BLOCK_HISTORY_PAGE_SIZE]
                next_cursor = (
                    self.cursor_codec.encode_history(
                        scope,
                        account_id,
                        relationship_id,
                        head.pair,
                        OperatorBlockHistoryPosition(
                            anchors,
                            visible[-1].changed_at,
                            visible[-1].blocker_id,
                            visible[-1].version,
                        ),
                    )
                    if len(rows) > OPERATOR_BLOCK_HISTORY_PAGE_SIZE
                    else None
                )
                result = OperatorBlockHistoryPage(
                    account_id,
                    relationship_id,
                    head.pair,
                    head.current_heads,
                    visible,
                    anchors,
                    next_cursor,
                )
            reference = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_ACCOUNT,
                    reference,
                    (reference,) if account is not None else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ
                    if account is not None
                    else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return result
