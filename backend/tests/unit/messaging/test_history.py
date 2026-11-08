from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.messaging.history import ReadMessageHistory
from studymate.application.messaging.history_cursors import (
    InvalidMessageHistoryCursorError,
    MessageHistoryCursor,
)
from studymate.application.messaging.history_ports import (
    MESSAGE_HISTORY_PAGE_SIZE,
    MessageHistoryTransaction,
    MessageHistoryWindow,
)
from studymate.application.messaging.ports import ConversationUnavailableError
from studymate.domain.messaging import ConfirmedMessage
from studymate.infrastructure.messaging.cursors import FernetMessageHistoryCursorCodec
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL
from tests.unit.test_message_commands import Store, sender, submission


class HistoryStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.forced: tuple[ConfirmedMessage, ...] | None = None
        self.expire_on_history = False

    @asynccontextmanager
    async def transaction(self, _conversation_id: UUID) -> AsyncIterator[MessageHistoryTransaction]:
        yield self

    async def history_messages(
        self, actor_id: UUID, conversation_id: UUID, window: MessageHistoryWindow
    ) -> tuple[ConfirmedMessage, ...]:
        assert actor_id == self.actor.session.account_id
        if self.expire_on_history:
            self.clock = self.actor.session.expires_at
        if self.forced is not None:
            return self.forced
        return tuple(
            sorted(
                (
                    operation.message
                    for operation in self.operations.values()
                    if operation.message is not None
                    and operation.conversation_id == conversation_id
                    and operation.message.sequence <= window.anchor_sequence
                    and (
                        window.before_sequence is None
                        or operation.message.sequence < window.before_sequence
                    )
                ),
                key=lambda message: message.sequence,
                reverse=True,
            )
        )[: MESSAGE_HISTORY_PAGE_SIZE + 1]


def read(store: HistoryStore) -> ReadMessageHistory:
    return ReadMessageHistory(
        store, Sha256SessionHasher(), FernetMessageHistoryCursorCodec.from_key(b"x" * 32)
    )


async def append(store: HistoryStore) -> ConfirmedMessage:
    operation = await sender(store)(replace(submission(store), intent_key=IntentKey(str(uuid4()))))
    assert operation.message is not None
    return operation.message


async def test_latest_page_is_ascending_and_original_anchor_excludes_later_messages() -> None:
    store = HistoryStore()
    for _ in range(MESSAGE_HISTORY_PAGE_SIZE + 1):
        await append(store)
    assert store.access is not None
    conversation = store.access.conversation.id
    latest = await read(store)(CREDENTIAL, conversation)
    assert len(latest.messages) == MESSAGE_HISTORY_PAGE_SIZE
    assert latest.messages[0].sequence < latest.messages[-1].sequence
    assert latest.next_cursor is not None
    original_anchor = latest.anchor_sequence
    await append(store)
    older = await read(store)(CREDENTIAL, conversation, latest.next_cursor)
    assert [message.sequence for message in older.messages] == [1]
    assert older.anchor_sequence == original_anchor
    assert older.next_cursor is None


async def test_empty_history_does_not_invent_messages_or_read_receipts() -> None:
    store = HistoryStore()
    assert store.access is not None
    page = await read(store)(CREDENTIAL, store.access.conversation.id)
    assert page.messages == ()
    assert page.anchor_sequence == 0
    assert page.next_cursor is None
    assert not store.operations
    assert not store.intents


async def test_history_survives_peer_unavailability_but_rechecks_actor() -> None:
    store = HistoryStore()
    message = await append(store)
    assert store.access is not None
    store.access = replace(store.access, peer_deleted=True, peer_banned=True, blocked=True)
    assert (await read(store)(CREDENTIAL, message.conversation_id)).messages == (message,)
    store.actor = replace(store.actor, activation_complete=False)
    with pytest.raises(StudentActionDeniedError):
        await read(store)(CREDENTIAL, message.conversation_id)
    store.actor = replace(store.actor, activation_complete=True)
    store.expire_on_history = True
    with pytest.raises(UnauthenticatedError):
        await read(store)(CREDENTIAL, message.conversation_id)


async def test_missing_membership_and_future_cursor_fail_closed() -> None:
    store = HistoryStore()
    assert store.access is not None
    conversation = store.access.conversation.id
    codec = FernetMessageHistoryCursorCodec.from_key(b"x" * 32)
    token = codec.encode(store.actor.session.account_id, conversation, MessageHistoryCursor(2, 1))
    with pytest.raises(InvalidMessageHistoryCursorError):
        await read(store)(CREDENTIAL, conversation, token)
    store.access = None
    with pytest.raises(ConversationUnavailableError):
        await read(store)(CREDENTIAL, conversation)


@pytest.mark.parametrize("violation", ["foreign", "repeated", "future", "unbounded"])
async def test_adapter_cannot_return_foreign_unbounded_or_unordered_private_payload(
    violation: str,
) -> None:
    store = HistoryStore()
    message = await append(store)
    if violation == "foreign":
        store.forced = (replace(message, conversation_id=uuid4()),)
    elif violation == "repeated":
        store.forced = (message, message)
    elif violation == "future":
        store.forced = (replace(message, sequence=message.sequence + 1),)
    else:
        store.forced = (message,) * (MESSAGE_HISTORY_PAGE_SIZE + 2)
    with pytest.raises(RuntimeError, match=r"bounded|scope|sequence"):
        await read(store)(CREDENTIAL, message.conversation_id)
