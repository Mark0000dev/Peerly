from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.messaging.commands import SendMessage
from studymate.application.messaging.read_positions import (
    AcknowledgeConversationRead,
    ReadConversationReadPosition,
    ReadPositionCommand,
    ReadPositionIntent,
    ReadPositionTransaction,
    ReadSequenceUnavailableError,
)
from studymate.domain.message_reads import ConversationReadPosition
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.test_message_commands import Store as MessageStore
from tests.unit.test_message_commands import submission

HASHER = Sha256SessionHasher()
FINGERPRINTER = HmacIntentFingerprinter(b"k" * 32)


class Store(MessageStore):
    def __init__(self) -> None:
        super().__init__()
        self.position: ConversationReadPosition | None = None
        self.read_intents: dict[IntentKey, ReadPositionIntent] = {}
        self.saved_positions: tuple[ConversationReadPosition, ...] = ()
        self.expire_read = False
        self.expire_after_ack = False
        self.missing_sequence = False

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[ReadPositionTransaction]:
        original = (self.position, self.read_intents.copy(), self.saved_positions)
        try:
            async with super().transaction(conversation_id):
                yield self
        except BaseException:
            self.position, self.read_intents, self.saved_positions = original
            raise

    async def read_position(
        self, actor_id: UUID, conversation_id: UUID
    ) -> ConversationReadPosition | None:
        assert actor_id == self.actor.session.account_id
        assert self.access is not None
        assert conversation_id == self.access.conversation.id
        if self.expire_read:
            self.clock = self.actor.session.expires_at
        return self.position

    async def read_position_intent(
        self, actor_id: UUID, key: IntentKey
    ) -> ReadPositionIntent | None:
        assert actor_id == self.actor.session.account_id
        return self.read_intents.get(key)

    async def message_sequence_exists(self, conversation_id: UUID, sequence: int) -> bool:
        assert self.access is not None
        assert conversation_id == self.access.conversation.id
        return not self.missing_sequence and any(
            value.message is not None and value.message.sequence == sequence
            for value in self.operations.values()
        )

    async def save_read_position(self, position: ConversationReadPosition) -> None:
        self.position = position
        self.saved_positions += (position,)
        if self.expire_after_ack:
            self.clock = self.actor.session.expires_at

    async def remember_read_position(
        self, actor_id: UUID, key: IntentKey, intent: ReadPositionIntent, at: datetime
    ) -> None:
        assert actor_id == self.actor.session.account_id
        assert at == self.clock
        self.read_intents[key] = intent


async def prepared() -> tuple[Store, ReadPositionCommand]:
    store = Store()
    command = submission(store)
    await SendMessage(store, HASHER, FINGERPRINTER)(command)
    return store, ReadPositionCommand(
        CREDENTIAL, command.conversation_id, 1, IntentKey(str(uuid4()))
    )


def acknowledger(store: Store) -> AcknowledgeConversationRead:
    return AcknowledgeConversationRead(store, HASHER, FINGERPRINTER)


async def test_read_never_fabricates_acknowledgement_and_ack_replays_original_revision() -> None:
    store, command = await prepared()
    read = ReadConversationReadPosition(store, HASHER)
    assert await read(CREDENTIAL, command.conversation_id) is None
    first = await acknowledger(store)(command)
    assert first.through_sequence == 1
    assert first.version == 1
    assert await read(CREDENTIAL, command.conversation_id) == first
    message = replace(submission(store), intent_key=IntentKey(str(uuid4())))
    await SendMessage(store, HASHER, FINGERPRINTER)(message)
    second = await acknowledger(store)(
        replace(command, through_sequence=2, key=IntentKey(str(uuid4())))
    )
    assert second.through_sequence == first.through_sequence + 1
    assert second.version == first.version + 1
    assert second.id != first.id
    assert await acknowledger(store)(command) == first
    assert await read(CREDENTIAL, command.conversation_id) == second
    assert await acknowledger(store)(replace(command, key=IntentKey(str(uuid4())))) == second
    assert store.saved_positions == (first, second)
    with pytest.raises(IdempotencyConflictError):
        await acknowledger(store)(replace(command, through_sequence=2))


@pytest.mark.parametrize("missing", [False, True])
async def test_ack_requires_an_actual_existing_sequence_not_a_future_or_missing_message(
    missing: bool,
) -> None:
    store, command = await prepared()
    store.missing_sequence = missing
    selected = command if missing else replace(command, through_sequence=2)
    with pytest.raises(ReadSequenceUnavailableError):
        await acknowledger(store)(selected)
    assert store.position is None
    assert not store.read_intents


@pytest.mark.parametrize("state", ["blocked", "deleted", "banned", "unverified"])
async def test_peer_contact_restrictions_do_not_freeze_private_history_read_state(
    state: str,
) -> None:
    store, command = await prepared()
    assert store.access is not None
    store.access = replace(
        store.access,
        blocked=state == "blocked",
        peer_deleted=state == "deleted",
        peer_banned=state == "banned",
        peer_verified=state != "unverified",
    )
    assert (await acknowledger(store)(command)).through_sequence == 1


async def test_session_expiry_rolls_back_position_revision_and_intent() -> None:
    store, command = await prepared()
    store.expire_after_ack = True
    with pytest.raises(UnauthenticatedError):
        await acknowledger(store)(command)
    assert store.position is None
    assert not store.saved_positions
    assert not store.read_intents


async def test_private_read_rechecks_session_after_source_lookup() -> None:
    store, command = await prepared()
    await acknowledger(store)(command)
    store.expire_read = True
    with pytest.raises(UnauthenticatedError):
        await ReadConversationReadPosition(store, HASHER)(CREDENTIAL, command.conversation_id)


async def test_adapter_cannot_substitute_another_private_read_source() -> None:
    store, command = await prepared()
    first = await acknowledger(store)(command)
    store.position = replace(first, conversation_id=uuid4())
    with pytest.raises(RuntimeError, match="another participant scope"):
        await ReadConversationReadPosition(store, HASHER)(CREDENTIAL, command.conversation_id)


@pytest.mark.parametrize("sequence", [0, -1, True])
def test_ack_commands_require_positive_sequence(sequence: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        ReadPositionCommand(CREDENTIAL, uuid4(), sequence, IntentKey("synthetic-read-key"))


def test_read_position_is_monotonic_even_when_wall_clock_metadata_does_not_advance() -> None:
    owner = UUID(int=2)
    position = ConversationReadPosition(
        uuid4(), uuid4(), AccountPair.between(owner, UUID(int=3)), owner, 1, 2, NOW
    )
    assert position.advance(1, NOW) is position
    assert position.advance(2, NOW) is position
    assert position.advance(3, NOW).through_sequence > position.through_sequence
    with pytest.raises(ValueError, match="positive"):
        position.advance(0, NOW)
    with pytest.raises(ValueError, match="participant"):
        replace(position, account_id=uuid4())
    with pytest.raises(ValueError, match="positive"):
        replace(position, version=True)
