from dataclasses import dataclass
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.conversation_index_ports import (
    OperatorConversationCursorCodec,
    OperatorConversationIndexUnitOfWork,
    OperatorConversationPosition,
)
from studymate.application.operator.cursors import OperatorCursorScope
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.conversation_index import (
    OPERATOR_CONVERSATION_PAGE_SIZE,
    OperatorConversationSummary,
)


@dataclass(frozen=True, slots=True)
class OperatorConversationsPage:
    account_id: UUID
    conversations: tuple[OperatorConversationSummary, ...]
    next_cursor: str | None


def validate_conversations(
    rows: tuple[OperatorConversationSummary, ...],
    account_id: UUID,
    position: OperatorConversationPosition | None,
) -> None:
    if len(rows) > OPERATOR_CONVERSATION_PAGE_SIZE + 1:
        raise RuntimeError("Conversation index source exceeded its bounded metadata page")
    previous = position.before_id.int if position is not None else None
    for row in rows:
        if not row.includes(account_id) or (previous is not None and row.id.int >= previous):
            raise RuntimeError(
                "Conversation index source violated actual participant or UUID ordering"
            )
        previous = row.id.int


@dataclass(frozen=True, slots=True)
class ReadOperatorConversations:
    unit_of_work: OperatorConversationIndexUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorConversationCursorCodec

    async def __call__(
        self, credential: SessionCredential, account_id: UUID, cursor: str | None = None
    ) -> OperatorConversationsPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.conversation_account(account_id)
            if actual is not None and actual != account_id:
                raise RuntimeError(
                    "Conversation index account source differs from requested target"
                )
            result = None
            if actual is not None:
                scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
                position = (
                    self.cursor_codec.decode_conversations(scope, account_id, cursor)
                    if cursor is not None
                    else None
                )
                rows = await transaction.indexed_conversations(account_id, position)
                validate_conversations(rows, account_id, position)
                visible = rows[:OPERATOR_CONVERSATION_PAGE_SIZE]
                next_cursor = (
                    self.cursor_codec.encode_conversations(
                        scope, account_id, OperatorConversationPosition(visible[-1].id)
                    )
                    if len(rows) > OPERATOR_CONVERSATION_PAGE_SIZE
                    else None
                )
                result = OperatorConversationsPage(account_id, visible, next_cursor)
            ref = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_ACCOUNT,
                    ref,
                    (ref,) if actual is not None else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ
                    if actual is not None
                    else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return result
