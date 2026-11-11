import asyncio
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import DateTime, cast, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from studymate.application.discovery.profiles import ReadDiscoveryProfile
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.messaging.commands import (
    CancelMessage,
    CancelMessageCommand,
    ReadMessageOutcome,
    SendMessage,
    SendMessageCommand,
)
from studymate.application.messaging.participants import (
    ChatParticipantState,
    ReadChatAvatar,
    ReadChatParticipant,
)
from studymate.application.messaging.ports import (
    ClientMessageConflictError,
    ConversationUnavailableError,
    MessageContactUnavailableError,
)
from studymate.application.profiles.goals import CompleteGoalCommand, CompleteOwnGoal, ReadOwnGoal
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.domain.messaging import MessageContent, MessageOperation, MessageOutcome
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.message_models import (
    MessageCommandIntentRecord,
    MessageOperationRecord,
    MessageRecord,
)
from studymate.infrastructure.persistence.messaging import (
    SqlMessageTransaction,
    SqlMessageUnitOfWork,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import complete_existing_setup
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.requests.fixture import (
    FINGERPRINTER,
    HASHER,
    Services,
    action,
    prepared,
    sent,
)
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class Chat:
    sender: Actor
    recipient: Actor
    api: Services
    conversation_id: UUID

    def send(self, recorder: "Recorder | None" = None) -> SendMessage:
        return SendMessage(
            SqlMessageUnitOfWork(
                self.api.sessions, recorder if recorder is not None else record_message_outcome
            ),
            HASHER,
            FINGERPRINTER,
        )

    def cancel(self) -> CancelMessage:
        return CancelMessage(
            SqlMessageUnitOfWork(self.api.sessions, record_message_outcome), HASHER, FINGERPRINTER
        )

    def read(self) -> ReadMessageOutcome:
        return ReadMessageOutcome(
            SqlMessageUnitOfWork(self.api.sessions, record_message_outcome), HASHER
        )

    def command(self, owner: Actor | None = None) -> SendMessageCommand:
        return SendMessageCommand(
            (owner if owner is not None else self.sender).credential,
            self.conversation_id,
            uuid4(),
            MessageContent("Synthetic private message\n  preserved indentation"),
            IntentKey(str(uuid4())),
        )


@dataclass(slots=True)
class Recorder:
    expire_actor: UUID | None = None
    fail: bool = False
    expired: bool = False

    async def __call__(self, session: AsyncSession, operation: MessageOperation) -> None:
        await record_message_outcome(session, operation)
        if self.expire_actor is not None:
            self.expired = True
        if self.fail:
            raise RuntimeError("Controlled message event failure")


async def chat(engine: AsyncEngine) -> Chat:
    sender, recipient, api = await prepared(engine)
    request = await sent(api, sender, recipient)
    accepted = await api.accept(action(recipient, sender, request))
    return Chat(sender, recipient, api, accepted.conversation.id)


async def test_actual_send_is_retained_and_replayed_without_new_sequence_or_event(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    command = owned.command()
    assert (
        await owned.read()(command.credential, command.conversation_id, command.client_message_id)
        is None
    )
    first = await owned.send()(command)
    assert first.message is not None
    assert first.message.content == command.content
    assert first.message.sequence == 1
    assert await owned.send()(command) == first
    assert await owned.send()(replace(command, intent_key=IntentKey(str(uuid4())))) == first
    assert (
        await owned.read()(command.credential, command.conversation_id, command.client_message_id)
        == first
    )
    with pytest.raises(IdempotencyConflictError):
        await owned.send()(replace(command, content=MessageContent("Edited intent")))
    with pytest.raises(ClientMessageConflictError):
        await owned.send()(
            replace(
                command, content=MessageContent("Edited intent"), intent_key=IntentKey(str(uuid4()))
            )
        )
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.message_operation_id == first.id)
            )
            == 1
        )
        record = await session.get(ConversationRecord, owned.conversation_id)
        assert record is not None
        assert record.next_message_sequence == first.message.sequence + 1


@pytest.mark.parametrize("cancel_first", [False, True])
async def test_both_committed_race_orders_have_one_truthful_terminal_outcome(
    identity_engine: AsyncEngine, cancel_first: bool
) -> None:
    owned = await chat(identity_engine)
    command = owned.command()
    cancel = CancelMessageCommand(
        command.credential,
        command.conversation_id,
        command.client_message_id,
        IntentKey(str(uuid4())),
    )
    if cancel_first:
        first = await owned.cancel()(cancel)
        second = await owned.send()(command)
        assert first.outcome == MessageOutcome.CANCELLED
    else:
        first = await owned.send()(command)
        second = await owned.cancel()(cancel)
        assert first.outcome == MessageOutcome.CONFIRMED
    assert first == second
    assert await owned.cancel()(cancel) == first
    assert (
        await owned.read()(command.credential, command.conversation_id, command.client_message_id)
        == first
    )
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(MessageOperationRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == int(
            not cancel_first
        )


async def test_parallel_bidirectional_sends_allocate_gapless_conversation_sequences(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    commands = tuple(
        owned.command(owned.sender if index % 2 == 0 else owned.recipient) for index in range(8)
    )
    results = await asyncio.wait_for(
        asyncio.gather(*(owned.send()(command) for command in commands)), timeout=15
    )
    assert sorted(
        result.message.sequence for result in results if result.message is not None
    ) == list(range(1, len(commands) + 1))
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == len(
            commands
        )


async def test_simultaneous_send_cancel_serializes_without_duplicate_or_false_cancel(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    command = owned.command()
    cancel = CancelMessageCommand(
        command.credential,
        command.conversation_id,
        command.client_message_id,
        IntentKey(str(uuid4())),
    )
    result = await asyncio.wait_for(
        asyncio.gather(owned.send()(command), owned.cancel()(cancel)), timeout=10
    )
    assert result[0] == result[1]
    assert await owned.send()(command) == result[0]


@pytest.mark.parametrize("failure", ["event", "expiry"])
async def test_failure_rolls_back_root_message_counter_intent_and_canonical_event(
    identity_engine: AsyncEngine, failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = await chat(identity_engine)
    recorder = Recorder(
        expire_actor=owned.sender.id if failure == "expiry" else None, fail=failure == "event"
    )
    original_now = SqlMessageTransaction.now

    async def clock(transaction: SqlMessageTransaction) -> datetime:
        if recorder.expired:
            expiry = await transaction.session.scalar(
                select(SessionRecord.expires_at).where(SessionRecord.account_id == owned.sender.id)
            )
            assert expiry is not None
            return expiry
        return await original_now(transaction)

    monkeypatch.setattr(SqlMessageTransaction, "now", clock)
    error = UnauthenticatedError if failure == "expiry" else RuntimeError
    with pytest.raises(error):
        await owned.send(recorder)(owned.command())
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(MessageOperationRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(MessageRecord)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(MessageCommandIntentRecord)) == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.message_operation_id.is_not(None))
            )
            == 0
        )
        record = await session.get(ConversationRecord, owned.conversation_id)
        assert record is not None
        assert record.next_message_sequence == 1
    recorder.expired = False
    assert (await owned.send()(owned.command())).message is not None


async def test_hidden_peers_continue_chat_and_deleted_peer_denies_only_new_send(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    command = owned.command()
    original = await owned.send()(command)
    visibility, _ = visibility_services(identity_engine)
    await visibility(visibility_command(owned.recipient))
    assert (await owned.send()(owned.command())).message is not None
    async with owned.api.sessions.begin() as session:
        at = await session.scalar(select(cast(func.clock_timestamp(), DateTime(timezone=True))))
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owned.recipient.id)
            .values(deleted_at=at)
        )
    assert await owned.send()(command) == original
    assert (
        await owned.read()(command.credential, command.conversation_id, command.client_message_id)
        == original
    )
    with pytest.raises(MessageContactUnavailableError):
        await owned.send()(owned.command())


async def test_unknown_and_foreign_conversations_share_neutral_unavailable(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    foreign = await actor(identity_engine)
    await ready_setup(identity_engine, foreign.credential)
    await complete_existing_setup(identity_engine, foreign)
    command = owned.command()
    with pytest.raises(ConversationUnavailableError):
        await owned.send()(replace(command, conversation_id=uuid4()))
    with pytest.raises(ConversationUnavailableError):
        await owned.send()(replace(command, credential=foreign.credential))


async def test_actual_pair_block_denies_new_send_but_retains_confirmed_history_and_cancel_recovery(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    command = owned.command()
    original = await owned.send()(command)
    profile = await ReadDiscoveryProfile(SqlDiscoveryProfileUnitOfWork(owned.api.sessions), HASHER)(
        owned.sender.credential, owned.recipient.id
    )
    block = ChangeOwnBlock(SqlBlockUnitOfWork(owned.api.sessions), HASHER, FINGERPRINTER)
    await block(
        ChangeBlockCommand(
            owned.sender.credential,
            owned.recipient.id,
            True,
            0,
            IntentKey(str(uuid4())),
            profile.access_context.id,
        )
    )
    assert await owned.send()(command) == original
    assert (
        await owned.cancel()(
            CancelMessageCommand(
                command.credential,
                command.conversation_id,
                command.client_message_id,
                IntentKey(str(uuid4())),
            )
        )
        == original
    )
    with pytest.raises(MessageContactUnavailableError):
        await owned.send()(owned.command())
    opposite = owned.command(owned.recipient)
    with pytest.raises(MessageContactUnavailableError):
        await owned.send()(opposite)


async def test_foreign_status_and_cancel_cannot_resolve_another_participants_client_id(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    command = owned.command()
    original = await owned.send()(command)
    # Even the other legitimate participant cannot inspect/cancel an author's
    # client operation. Their same UUID is a separate logical authored intent.
    assert (
        await owned.read()(
            owned.recipient.credential, command.conversation_id, command.client_message_id
        )
        is None
    )
    other = await owned.cancel()(
        CancelMessageCommand(
            owned.recipient.credential,
            command.conversation_id,
            command.client_message_id,
            IntentKey(str(uuid4())),
        )
    )
    assert other.outcome == MessageOutcome.CANCELLED
    assert other.id != original.id
    assert (
        await owned.read()(command.credential, command.conversation_id, command.client_message_id)
        == original
    )


@pytest.mark.parametrize(
    "malformation", ["missing_message", "duplicate_client", "wrong_pair", "false_cancel_event"]
)
async def test_database_enforces_terminal_source_logical_uniqueness_and_canonical_state(
    identity_engine: AsyncEngine,
    malformation: str,
) -> None:
    owned = await chat(identity_engine)
    command = owned.command()
    original = await owned.send()(command)
    assert original.message is not None
    sent_at = original.message.sent_at

    async def violate() -> None:
        async with owned.api.sessions.begin() as session:
            if malformation == "false_cancel_event":
                session.add(
                    ProductEventRecord(
                        id=uuid4(),
                        account_id=owned.sender.id,
                        kind="message.cancelled",
                        occurrence_key=str(uuid4()),
                        schema_version=1,
                        occurred_at=sent_at,
                        message_operation_id=original.id,
                        message_operation_state="cancelled",
                    )
                )
            else:
                session.add(
                    MessageOperationRecord(
                        id=uuid4(),
                        conversation_id=owned.conversation_id,
                        low_id=original.pair.low,
                        high_id=uuid4() if malformation == "wrong_pair" else original.pair.high,
                        author_id=owned.sender.id,
                        client_message_id=command.client_message_id
                        if malformation == "duplicate_client"
                        else uuid4(),
                        state="confirmed" if malformation == "missing_message" else "cancelled",
                        message_id=uuid4() if malformation == "missing_message" else None,
                        cancelled_at=None if malformation == "missing_message" else sent_at,
                    )
                )
            await session.flush()

    with pytest.raises(IntegrityError):
        await violate()
    assert (
        await owned.read()(command.credential, command.conversation_id, command.client_message_id)
        == original
    )


async def test_minimal_current_chat_identity_survives_hidden_exposure_pause_and_context_completion(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    uow = SqlMessageUnitOfWork(owned.api.sessions, record_message_outcome)
    read = ReadChatParticipant(uow, HASHER)
    original = await read(owned.sender.credential, owned.conversation_id)
    assert original.state == ChatParticipantState.AVAILABLE
    assert original.name is not None
    assert original.photo_version is not None
    visibility, _ = visibility_services(identity_engine)
    await visibility(visibility_command(owned.recipient))
    goals = SqlGoalUnitOfWork(owned.api.sessions)
    current = await ReadOwnGoal(goals, HASHER)(owned.recipient.credential)
    assert current is not None
    await CompleteOwnGoal(goals, HASHER, FINGERPRINTER)(
        CompleteGoalCommand(
            owned.recipient.credential,
            current.goal.id,
            current.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    async with owned.api.sessions.begin() as session:
        exposure = await session.get(DiscoveryExposureRecord, owned.recipient.id)
        assert exposure is not None
        exposure.paused_at = exposure.last_activity_at
    assert await read(owned.sender.credential, owned.conversation_id) == original
    assert (await owned.send()(owned.command())).message is not None
    async with owned.api.sessions.begin() as session:
        at = await session.scalar(select(cast(func.clock_timestamp(), DateTime(timezone=True))))
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == owned.recipient.id)
            .values(deleted_at=at)
        )
    deleted = await read(owned.sender.credential, owned.conversation_id)
    assert deleted.state == ChatParticipantState.DELETED
    assert deleted.name is None
    assert deleted.photo_version is None


@pytest.mark.parametrize("delete_during_read", [False, True])
async def test_chat_avatar_releases_sole_sql_connection_and_rechecks_participant(
    identity_engine: AsyncEngine,
    delete_during_read: bool,
) -> None:
    owned = await chat(identity_engine)
    visibility, _ = visibility_services(identity_engine)
    await visibility(visibility_command(owned.recipient))
    async with identity_engine.connect() as connection:
        schema = await connection.scalar(select(func.current_schema()))
    assert isinstance(schema, str)
    engine = create_async_engine(
        identity_engine.url,
        pool_size=1,
        max_overflow=0,
        connect_args={"server_settings": {"search_path": schema}},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    read = ReadChatParticipant(SqlMessageUnitOfWork(sessions, record_message_outcome), HASHER)
    participant = await read(owned.sender.credential, owned.conversation_id)
    assert participant.photo_version is not None

    @dataclass(slots=True)
    class Storage:
        reads: int = 0

        async def read(self, reference: MediaObjectRef) -> bytes:
            assert reference.kind == MediaObjectKind.DISPLAY
            # A separate storage task can acquire the sole connection: neither
            # SQL transaction nor permission lock spans this external-I/O boundary.
            async with asyncio.timeout(2):
                async with sessions.begin() as session:
                    assert await session.scalar(select(func.current_schema())) == schema
                    if delete_during_read:
                        at = await session.scalar(
                            select(cast(func.clock_timestamp(), DateTime(timezone=True)))
                        )
                        await session.execute(
                            update(AccountRecord)
                            .where(AccountRecord.id == owned.recipient.id)
                            .values(deleted_at=at)
                        )
            self.reads += 1
            return b"synthetic-display-content"

    storage = Storage()
    avatar = ReadChatAvatar(SqlMessageUnitOfWork(sessions, record_message_outcome), HASHER, storage)
    try:
        if delete_during_read:
            with pytest.raises(ConversationUnavailableError):
                await avatar(
                    owned.sender.credential, owned.conversation_id, participant.photo_version
                )
        else:
            assert (
                await avatar(
                    owned.sender.credential, owned.conversation_id, participant.photo_version
                )
                == b"synthetic-display-content"
            )
        assert storage.reads == 1
    finally:
        await engine.dispose()
