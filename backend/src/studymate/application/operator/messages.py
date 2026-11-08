from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import (
    InvalidOperatorCursorError,
    OperatorCursorCodec,
    OperatorCursorScope,
)
from studymate.application.operator.ports import (
    OperatorMessagePosition,
    OperatorMessageUnitOfWork,
    OperatorMessageWindow,
)
from studymate.domain.messaging import ChatConversation, ConfirmedMessage
from studymate.domain.operator.audit import (
    OPERATOR_MESSAGE_PAGE_SIZE,
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)


@dataclass(frozen=True, slots=True)
class OperatorConversationMessagesPage:
    conversation: ChatConversation
    messages: tuple[ConfirmedMessage, ...] = field(repr=False)
    next_cursor: str | None
    anchor_sequence: int


@dataclass(frozen=True, slots=True)
class ReadOperatorConversationMessages:
    unit_of_work: OperatorMessageUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorCursorCodec

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID, cursor: str | None = None
    ) -> OperatorConversationMessagesPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            conversation = await transaction.operator_conversation(conversation_id)
            resource = OperatorResourceRef(OperatorResourceKind.CONVERSATION, conversation_id)
            if conversation is None:
                await transaction.save_operator_audit(
                    OperatorAudit(
                        uuid4(),
                        principal.access,
                        OperatorAction.READ_CONVERSATION_MESSAGES,
                        resource,
                        (),
                        await transaction.now(),
                        OperatorAuditOutcome.NOT_FOUND,
                    )
                )
                await finish_operator(transaction, principal)
                return None
            if conversation.id != conversation_id:
                raise RuntimeError("Operator conversation projection belongs to another resource")
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_messages(scope, conversation_id, cursor)
                if cursor is not None
                else None
            )
            latest = conversation.next_message_sequence - 1
            if position is not None and position.anchor_sequence > latest:
                raise InvalidOperatorCursorError
            anchor = latest if position is None else position.anchor_sequence
            window = OperatorMessageWindow(
                anchor, position.before_sequence if position is not None else None
            )
            rows = await transaction.operator_messages(conversation_id, window)
            if len(rows) > OPERATOR_MESSAGE_PAGE_SIZE + 1:
                raise RuntimeError("Operator message inspection exceeded its bounded page")
            previous = anchor + 1
            for message in rows:
                if (
                    message.conversation_id != conversation_id
                    or message.pair != conversation.pair
                    or message.sequence >= previous
                    or (
                        window.before_sequence is not None
                        and message.sequence >= window.before_sequence
                    )
                ):
                    raise RuntimeError(
                        "Operator message inspection violates actual source ordering"
                    )
                previous = message.sequence
            visible = rows[:OPERATOR_MESSAGE_PAGE_SIZE]
            next_cursor = (
                self.cursor_codec.encode_messages(
                    scope, conversation_id, OperatorMessagePosition(anchor, visible[-1].sequence)
                )
                if len(rows) > OPERATOR_MESSAGE_PAGE_SIZE
                else None
            )
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_CONVERSATION_MESSAGES,
                    resource,
                    tuple(
                        OperatorResourceRef(OperatorResourceKind.MESSAGE, message.id)
                        for message in reversed(visible)
                    ),
                    await transaction.now(),
                    OperatorAuditOutcome.READ,
                )
            )
            await finish_operator(transaction, principal)
            return OperatorConversationMessagesPage(
                conversation, tuple(reversed(visible)), next_cursor, anchor
            )
