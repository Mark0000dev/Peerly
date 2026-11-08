from dataclasses import dataclass
from uuid import UUID

from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
)
from studymate.application.messaging.commands import authorize_conversation
from studymate.application.messaging.history_cursors import (
    InvalidMessageHistoryCursorError,
    MessageHistoryCursor,
    MessageHistoryCursorCodec,
)
from studymate.application.messaging.history_ports import (
    MESSAGE_HISTORY_PAGE_SIZE,
    MessageHistoryPage,
    MessageHistoryUnitOfWork,
    MessageHistoryWindow,
)


@dataclass(frozen=True, slots=True)
class ReadMessageHistory:
    unit_of_work: MessageHistoryUnitOfWork
    hasher: SessionHasher
    cursor_codec: MessageHistoryCursorCodec

    async def __call__(
        self, credential: SessionCredential, conversation_id: UUID, cursor: str | None = None
    ) -> MessageHistoryPage:
        async with self.unit_of_work.transaction(conversation_id) as transaction:
            actor, access = await authorize_conversation(
                transaction, self.hasher, credential, conversation_id
            )
            actor_id = actor.session.account_id
            position = (
                self.cursor_codec.decode(actor_id, conversation_id, cursor)
                if cursor is not None
                else None
            )
            latest = access.conversation.next_message_sequence - 1
            if position is not None and position.anchor_sequence > latest:
                raise InvalidMessageHistoryCursorError
            anchor = latest if position is None else position.anchor_sequence
            window = MessageHistoryWindow(
                anchor, position.before_sequence if position is not None else None
            )
            rows = await transaction.history_messages(actor_id, conversation_id, window)
            if len(rows) > MESSAGE_HISTORY_PAGE_SIZE + 1:
                raise RuntimeError("Message history exceeded its bounded page")
            previous = anchor + 1
            for message in rows:
                if (
                    message.conversation_id != conversation_id
                    or message.pair != access.conversation.pair
                    or message.sequence >= previous
                    or (
                        window.before_sequence is not None
                        and message.sequence >= window.before_sequence
                    )
                ):
                    raise RuntimeError(
                        "History projection violates accepted scope or sequence order"
                    )
                previous = message.sequence
            visible = rows[:MESSAGE_HISTORY_PAGE_SIZE]
            next_cursor = (
                self.cursor_codec.encode(
                    actor_id, conversation_id, MessageHistoryCursor(anchor, visible[-1].sequence)
                )
                if len(rows) > MESSAGE_HISTORY_PAGE_SIZE
                else None
            )
            result = MessageHistoryPage(tuple(reversed(visible)), next_cursor, anchor)
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
