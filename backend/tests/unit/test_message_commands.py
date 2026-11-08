from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.messaging.commands import (
    CancelMessage,
    CancelMessageCommand,
    ReadMessageOutcome,
    SendMessage,
    SendMessageCommand,
)
from studymate.application.messaging.ports import (
    ClientMessageConflictError,
    ConversationAccess,
    ConversationUnavailableError,
    MessageContactUnavailableError,
    MessageImageUnavailableError,
    MessageIntent,
    MessageTransaction,
)
from studymate.domain.messaging import (
    ChatConversation,
    MessageContent,
    MessageOperation,
    MessageOutcome,
)
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        pair = AccountPair.between(self.actor.session.account_id, UUID(int=3))
        self.access: ConversationAccess | None = ConversationAccess(
            ChatConversation(uuid4(), uuid4(), pair, uuid4(), 2, 1), True, False, False, False
        )
        self.operations: dict[UUID, MessageOperation] = {}
        self.cancelled_preparation_ids: list[UUID] = []
        self.fail_cleanup = False
        self.intents: dict[tuple[str, IntentKey], MessageIntent] = {}
        self.expire_on_save = False
        self.expire_on_intent_read = False
        self.expire_on_operation_read = False

    @asynccontextmanager
    async def transaction(self, _conversation_id: UUID) -> AsyncIterator[MessageTransaction]:
        previous = (
            self.operations.copy(),
            self.intents.copy(),
            self.access,
            self.cancelled_preparation_ids.copy(),
        )
        try:
            yield self
        except BaseException:
            self.operations, self.intents, self.access, self.cancelled_preparation_ids = previous
            raise

    async def conversation(
        self, actor_id: UUID, _conversation_id: UUID
    ) -> ConversationAccess | None:
        assert actor_id == self.actor.session.account_id
        return self.access

    async def message_intent(
        self, actor_id: UUID, operation: str, key: IntentKey
    ) -> MessageIntent | None:
        assert actor_id == self.actor.session.account_id
        result = self.intents.get((operation, key))
        if self.expire_on_intent_read:
            self.clock = self.actor.session.expires_at
        return result

    async def message_operation(
        self, actor_id: UUID, _conversation_id: UUID, client_message_id: UUID
    ) -> MessageOperation | None:
        assert actor_id == self.actor.session.account_id
        result = self.operations.get(client_message_id)
        if self.expire_on_operation_read:
            self.clock = self.actor.session.expires_at
        return result

    async def admit_message_content(
        self,
        actor_id: UUID,
        conversation_id: UUID,
        client_message_id: UUID,
        content: MessageContent,
    ) -> None:
        assert actor_id == self.actor.session.account_id
        assert self.access is not None
        assert conversation_id == self.access.conversation.id
        assert client_message_id not in self.operations
        if content.image_id is not None:
            raise MessageImageUnavailableError

    async def save_message_operation(self, operation: MessageOperation) -> None:
        assert operation.client_message_id not in self.operations
        self.operations[operation.client_message_id] = operation
        assert self.access is not None
        if operation.message is not None:
            self.access = replace(
                self.access,
                conversation=replace(
                    self.access.conversation, next_message_sequence=operation.message.sequence + 1
                ),
            )
        if self.expire_on_save:
            self.clock = self.actor.session.expires_at

    async def cancel_image_preparation(self, operation: MessageOperation) -> None:
        assert operation.author_id == self.actor.session.account_id
        assert operation.cancelled_at is not None
        self.cancelled_preparation_ids.append(operation.id)
        if self.fail_cleanup:
            raise RuntimeError("Synthetic preparation cleanup failure")

    async def remember_message_intent(
        self, actor_id: UUID, operation: str, key: IntentKey, intent: MessageIntent, at: datetime
    ) -> None:
        assert actor_id == self.actor.session.account_id
        assert at == self.clock
        self.intents[operation, key] = intent


def submission(store: Store) -> SendMessageCommand:
    assert store.access is not None
    return SendMessageCommand(
        CREDENTIAL,
        store.access.conversation.id,
        uuid4(),
        MessageContent("Synthetic private study message"),
        IntentKey("synthetic-message-send"),
    )


def sender(store: Store) -> SendMessage:
    return SendMessage(store, Sha256SessionHasher(), HmacIntentFingerprinter(b"k" * 32))


def canceller(store: Store) -> CancelMessage:
    return CancelMessage(store, Sha256SessionHasher(), HmacIntentFingerprinter(b"k" * 32))


def cancel(command: SendMessageCommand) -> CancelMessageCommand:
    return CancelMessageCommand(
        command.credential,
        command.conversation_id,
        command.client_message_id,
        IntentKey("synthetic-message-cancel"),
    )


async def test_send_replays_original_without_allocating_another_sequence() -> None:
    store = Store()
    command = submission(store)
    first = await sender(store)(command)
    assert first.outcome == MessageOutcome.CONFIRMED
    assert first.message is not None
    assert first.message.sequence == 1
    assert await sender(store)(command) == first
    assert await sender(store)(replace(command, intent_key=IntentKey("new-transport-key"))) == first
    assert len(store.operations) == 1
    assert store.access is not None
    assert store.access.conversation.next_message_sequence == first.message.sequence + 1
    with pytest.raises(IdempotencyConflictError):
        await sender(store)(replace(command, content=MessageContent("Changed private content")))
    with pytest.raises(ClientMessageConflictError):
        await sender(store)(
            replace(
                command,
                content=MessageContent("Changed private content"),
                intent_key=IntentKey("another-transport-key"),
            )
        )


async def test_cancel_winner_is_retained_and_prevents_a_delayed_send() -> None:
    store = Store()
    command = submission(store)
    first = await canceller(store)(cancel(command))
    assert first.outcome == MessageOutcome.CANCELLED
    assert await canceller(store)(cancel(command)) == first
    assert await sender(store)(command) == first
    assert first.message is None
    assert store.cancelled_preparation_ids == [first.id]
    assert store.access is not None
    assert store.access.conversation.next_message_sequence == 1
    assert len(store.operations) == 1


async def test_confirmed_send_winner_is_truthfully_returned_by_cancel_and_status() -> None:
    store = Store()
    command = submission(store)
    read = ReadMessageOutcome(store, Sha256SessionHasher())
    assert (
        await read(command.credential, command.conversation_id, command.client_message_id) is None
    )
    first = await sender(store)(command)
    assert await canceller(store)(cancel(command)) == first
    assert store.cancelled_preparation_ids == []
    assert (
        await read(command.credential, command.conversation_id, command.client_message_id) == first
    )

    second = await sender(store)(
        replace(command, client_message_id=uuid4(), intent_key=IntentKey("second-message-key"))
    )
    assert first.message is not None
    assert second.message is not None
    assert second.message.sequence == first.message.sequence + 1
    assert second.message.sent_at == first.message.sent_at


async def test_cleanup_failure_rolls_back_cancellation_and_its_receipt() -> None:
    store = Store()
    command = submission(store)
    store.fail_cleanup = True
    with pytest.raises(RuntimeError, match="preparation cleanup failure"):
        await canceller(store)(cancel(command))
    assert not store.operations
    assert not store.intents
    assert not store.cancelled_preparation_ids


@pytest.mark.parametrize("capability", ["blocked", "peer_banned", "peer_deleted", "peer_verified"])
async def test_current_peer_contact_denies_only_new_send_not_retained_outcome(
    capability: str,
) -> None:
    store = Store()
    command = submission(store)
    first = await sender(store)(command)
    assert store.access is not None
    store.access = replace(
        store.access,
        blocked=capability == "blocked",
        peer_banned=capability == "peer_banned",
        peer_deleted=capability == "peer_deleted",
        peer_verified=capability != "peer_verified",
    )
    assert await sender(store)(command) == first
    assert await canceller(store)(cancel(command)) == first
    assert (
        await ReadMessageOutcome(store, Sha256SessionHasher())(
            CREDENTIAL, command.conversation_id, command.client_message_id
        )
        == first
    )
    with pytest.raises(MessageContactUnavailableError):
        await sender(store)(
            replace(command, client_message_id=uuid4(), intent_key=IntentKey("denied-new-message"))
        )


@pytest.mark.parametrize("operation", ["send", "cancel"])
async def test_expiry_at_terminal_write_rolls_back_operation_sequence_and_receipt(
    operation: str,
) -> None:
    store = Store()
    command = submission(store)
    original = store.access
    store.expire_on_save = True
    result = sender(store)(command) if operation == "send" else canceller(store)(cancel(command))
    with pytest.raises(UnauthenticatedError):
        await result
    assert not store.operations
    assert not store.intents
    assert store.access == original


@pytest.mark.parametrize("state", ["unverified", "banned", "deleted", "not_activated"])
async def test_current_actor_guard_is_required_even_for_recovery(state: str) -> None:
    store = Store()
    command = submission(store)
    await sender(store)(command)
    store.actor = replace(
        store.actor,
        membership=None if state == "unverified" else store.actor.membership,
        banned=state == "banned",
        deleted_at=NOW if state == "deleted" else None,
        activation_complete=state != "not_activated",
    )
    expected = UnauthenticatedError if state == "deleted" else StudentActionDeniedError
    with pytest.raises(expected):
        await sender(store)(command)
    with pytest.raises(expected):
        await ReadMessageOutcome(store, Sha256SessionHasher())(
            CREDENTIAL, command.conversation_id, command.client_message_id
        )


async def test_no_conversation_is_neutral_and_wrong_adapter_scope_fails_closed() -> None:
    store = Store()
    command = submission(store)
    original = store.access
    store.access = None
    with pytest.raises(ConversationUnavailableError):
        await sender(store)(command)
    store.access = original
    with pytest.raises(RuntimeError, match="participant scope"):
        await sender(store)(replace(command, conversation_id=uuid4()))
    assert not store.operations


async def test_image_reference_alone_cannot_create_a_confirmed_message() -> None:
    store = Store()
    command = replace(submission(store), content=MessageContent(image_id=uuid4()))
    with pytest.raises(MessageImageUnavailableError):
        await sender(store)(command)
    assert not store.operations
    assert not store.intents


@pytest.mark.parametrize("operation", ["send", "cancel"])
async def test_replay_cannot_outlive_current_session_during_receipt_lookup(operation: str) -> None:
    store = Store()
    command = submission(store)
    if operation == "send":
        await sender(store)(command)
    else:
        await canceller(store)(cancel(command))
    store.expire_on_intent_read = True
    result = sender(store)(command) if operation == "send" else canceller(store)(cancel(command))
    with pytest.raises(UnauthenticatedError):
        await result
    assert len(store.operations) == 1


async def test_unobserved_status_still_rechecks_session_after_its_owned_lookup() -> None:
    store = Store()
    command = submission(store)
    store.expire_on_operation_read = True
    with pytest.raises(UnauthenticatedError):
        await ReadMessageOutcome(store, Sha256SessionHasher())(
            CREDENTIAL, command.conversation_id, command.client_message_id
        )
