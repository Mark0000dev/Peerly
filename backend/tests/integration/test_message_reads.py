import asyncio
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.messaging.read_positions import (
    AcknowledgeConversationRead,
    ReadConversationReadPosition,
    ReadPositionCommand,
    ReadSequenceUnavailableError,
)
from studymate.domain.message_reads import ConversationReadPosition
from studymate.infrastructure.persistence.message_read_models import (
    ConversationReadPositionRecord,
    ConversationReadRevisionRecord,
)
from studymate.infrastructure.persistence.message_reads import SqlReadPositionUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_conversation_read,
    record_message_outcome,
)
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class Recorder:
    fail: bool = False

    async def __call__(self, session: AsyncSession, position: ConversationReadPosition) -> None:
        await record_conversation_read(session, position)
        if self.fail:
            raise RuntimeError("Controlled read marker canonical failure")


def uow(owned: Chat, *, fail: bool = False) -> SqlReadPositionUnitOfWork:
    return SqlReadPositionUnitOfWork(owned.api.sessions, record_message_outcome, Recorder(fail))


def command(owned: Chat, sequence: int) -> ReadPositionCommand:
    return ReadPositionCommand(
        owned.recipient.credential, owned.conversation_id, sequence, IntentKey(str(uuid4()))
    )


async def test_actual_read_ack_is_private_monotonic_and_original_receipts_survive_later_progress(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    first_message = await owned.send()(owned.command())
    assert first_message.message is not None
    service = AcknowledgeConversationRead(uow(owned), HASHER, FINGERPRINTER)
    read = ReadConversationReadPosition(uow(owned), HASHER)
    assert await read(owned.recipient.credential, owned.conversation_id) is None
    initial = command(owned, first_message.message.sequence)
    first = await service(initial)
    second_message = await owned.send()(owned.command())
    assert second_message.message is not None
    second = await service(command(owned, second_message.message.sequence))
    assert second.version == first.version + 1
    assert second.through_sequence > first.through_sequence
    assert await service(initial) == first
    assert await service(command(owned, first.through_sequence)) == second
    assert await read(owned.recipient.credential, owned.conversation_id) == second
    assert await read(owned.sender.credential, owned.conversation_id) is None
    with pytest.raises(IdempotencyConflictError):
        await service(replace(initial, through_sequence=second.through_sequence))
    async with owned.api.sessions() as session:
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.conversation_read_id.is_not(None)
                )
            )
        )
        assert {event.conversation_read_id for event in events} == {first.id, second.id}
        assert all(event.account_id == owned.recipient.id for event in events)
        assert all(event.read_conversation_id == owned.conversation_id for event in events)


async def test_parallel_read_positions_keep_highest_source_without_duplicate_revisions(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    for _ in range(3):
        await owned.send()(owned.command())
    service = AcknowledgeConversationRead(uow(owned), HASHER, FINGERPRINTER)
    results = await asyncio.wait_for(
        asyncio.gather(*(service(command(owned, sequence)) for sequence in (2, 3, 1, 3))),
        timeout=10,
    )
    current = await ReadConversationReadPosition(uow(owned), HASHER)(
        owned.recipient.credential, owned.conversation_id
    )
    assert current is not None
    assert current.through_sequence == max(result.through_sequence for result in results)
    async with owned.api.sessions() as session:
        revisions = tuple(
            await session.scalars(
                select(ConversationReadRevisionRecord).order_by(
                    ConversationReadRevisionRecord.version
                )
            )
        )
        sequences = tuple(revision.through_sequence for revision in revisions)
        assert sequences == tuple(sorted(set(sequences)))
        assert all(revision.account_id == owned.recipient.id for revision in revisions)


async def test_future_read_position_is_not_a_placeholder_and_get_never_acknowledges(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    service = AcknowledgeConversationRead(uow(owned), HASHER, FINGERPRINTER)
    with pytest.raises(ReadSequenceUnavailableError):
        await service(command(owned, 1))
    assert (
        await ReadConversationReadPosition(uow(owned), HASHER)(
            owned.recipient.credential, owned.conversation_id
        )
        is None
    )
    async with owned.api.sessions() as session:
        assert (
            await session.get(
                ConversationReadPositionRecord, (owned.conversation_id, owned.recipient.id)
            )
            is None
        )


async def test_read_event_failure_rolls_back_root_revision_and_intent_then_retries(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    await owned.send()(owned.command())
    current = command(owned, 1)
    with pytest.raises(RuntimeError, match="Controlled read marker"):
        await AcknowledgeConversationRead(uow(owned, fail=True), HASHER, FINGERPRINTER)(current)
    assert (
        await ReadConversationReadPosition(uow(owned), HASHER)(
            owned.recipient.credential, owned.conversation_id
        )
        is None
    )
    saved = await AcknowledgeConversationRead(uow(owned), HASHER, FINGERPRINTER)(current)
    assert saved.version == 1


@pytest.mark.parametrize("malformation", ["foreign_actor", "future_sequence", "mixed_event"])
async def test_read_source_constraints_reject_foreign_future_and_mixed_sources(
    identity_engine: AsyncEngine, malformation: str
) -> None:
    owned = await chat(identity_engine)
    await owned.send()(owned.command())
    saved = await AcknowledgeConversationRead(uow(owned), HASHER, FINGERPRINTER)(command(owned, 1))

    async def violate() -> None:
        async with owned.api.sessions.begin() as session:
            if malformation == "mixed_event":
                session.add(
                    ProductEventRecord(
                        id=uuid4(),
                        account_id=owned.recipient.id,
                        kind="conversation.read_acknowledged",
                        occurrence_key=str(uuid4()),
                        schema_version=1,
                        occurred_at=saved.acknowledged_at,
                        conversation_read_id=saved.id,
                        read_conversation_id=owned.conversation_id,
                        goal_id=uuid4(),
                    )
                )
            else:
                session.add(
                    ConversationReadRevisionRecord(
                        id=uuid4(),
                        conversation_id=owned.conversation_id,
                        account_id=UUID(int=999)
                        if malformation == "foreign_actor"
                        else owned.sender.id,
                        version=1,
                        low_id=saved.pair.low,
                        high_id=saved.pair.high,
                        through_sequence=999 if malformation == "future_sequence" else 1,
                        acknowledged_at=saved.acknowledged_at,
                    )
                )
            await session.flush()

    with pytest.raises(IntegrityError):
        await violate()
