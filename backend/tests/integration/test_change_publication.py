import asyncio
from dataclasses import dataclass

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.changes.publication import (
    PUBLICATION_BATCH_SIZE,
    PublishChanges,
)
from studymate.application.messaging.commands import SendMessage
from studymate.domain.messaging import MessageOperation
from studymate.infrastructure.changes.models import (
    ChangeHeadRecord,
    ChangeOutboxRecord,
    PublishedChangeRecord,
)
from studymate.infrastructure.changes.publication import SqlChangePublicationUnitOfWork
from studymate.infrastructure.changes.staging import stage_change_outbox
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.messaging import SqlMessageUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_message_outcome
from tests.integration.change_fixture import drain, head_positions, message_events, stage
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_staging_never_spends_sequences_and_reconciliation_never_duplicates_published_source(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    await owned.send()(owned.command())
    events = await message_events(owned)
    await stage(owned, events)
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ChangeHeadRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(PublishedChangeRecord)) == 0
        assert {row.recipient_id for row in await session.scalars(select(ChangeOutboxRecord))} == {
            owned.sender.id,
            owned.recipient.id,
        }
    async with owned.api.sessions() as session:
        expected = {
            (row.canonical_event_id, row.recipient_id)
            for row in await session.scalars(select(ChangeOutboxRecord))
        }
    publish = PublishChanges(SqlChangePublicationUnitOfWork(owned.api.sessions))
    assert await publish() == len(expected)
    await stage(owned, events)
    assert await publish() == 0
    async with owned.api.sessions() as session:
        rows = tuple(await session.scalars(select(PublishedChangeRecord)))
        assert {(row.canonical_event_id, row.recipient_id) for row in rows} == expected
        assert {row.recipient_id for row in rows if row.canonical_event_id == events[0].id} == {
            owned.sender.id,
            owned.recipient.id,
        }
        for recipient in (owned.sender.id, owned.recipient.id):
            sequences = sorted(row.sequence for row in rows if row.recipient_id == recipient)
            assert sequences == list(range(1, len(sequences) + 1))


async def test_delayed_legacy_transport_reconciliation_cannot_leave_a_timestamp_cursor_gap(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    await drain(owned)
    baseline = await head_positions(owned)
    await owned.send()(owned.command())
    await owned.send()(owned.command())
    old, new = await message_events(owned)
    # Controlled legacy transport-index loss only: canonical/business records stay intact.
    # It models a retained pre-transport source being reconciled after later sources.
    async with owned.api.sessions.begin() as session:
        await session.execute(
            delete(ChangeOutboxRecord).where(
                ChangeOutboxRecord.canonical_event_id == old.id,
                ChangeOutboxRecord.published_sequence.is_(None),
            )
        )
    publish = PublishChanges(SqlChangePublicationUnitOfWork(owned.api.sessions))
    async with owned.api.sessions.begin() as delayed:
        await stage_change_outbox(delayed, old)
        await stage(owned, (new,))
        assert await publish() == len((owned.sender, owned.recipient))
    assert await publish() == len((owned.sender, owned.recipient))
    async with owned.api.sessions() as session:
        for recipient in (owned.sender.id, owned.recipient.id):
            rows = tuple(
                await session.scalars(
                    select(PublishedChangeRecord)
                    .where(
                        PublishedChangeRecord.recipient_id == recipient,
                        PublishedChangeRecord.canonical_event_id.in_((old.id, new.id)),
                    )
                    .order_by(PublishedChangeRecord.sequence)
                )
            )
            assert tuple(row.canonical_event_id for row in rows) == (new.id, old.id)
            assert tuple(row.sequence for row in rows) == (
                baseline.get(recipient, 0) + 1,
                baseline.get(recipient, 0) + 2,
            )


async def test_two_publishers_with_overlapping_recipient_heads_publish_once_without_sequence_holes(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    await drain(owned)
    baseline = await head_positions(owned)
    source_count = PUBLICATION_BATCH_SIZE // 2 + 1
    for _ in range(source_count):
        await owned.send()(owned.command())
    events = await message_events(owned)
    assert len(events) == source_count
    await stage(owned, events)
    publish = PublishChanges(SqlChangePublicationUnitOfWork(owned.api.sessions))
    counts = await asyncio.gather(publish(), publish())
    assert sum(counts) == source_count * len((owned.sender, owned.recipient))
    assert await publish() == 0
    async with owned.api.sessions() as session:
        for recipient in (owned.sender.id, owned.recipient.id):
            rows = tuple(
                await session.scalars(
                    select(PublishedChangeRecord)
                    .where(
                        PublishedChangeRecord.recipient_id == recipient,
                        PublishedChangeRecord.canonical_event_id.in_(
                            tuple(event.id for event in events)
                        ),
                    )
                    .order_by(PublishedChangeRecord.sequence)
                )
            )
            assert tuple(row.sequence for row in rows) == tuple(
                range(baseline.get(recipient, 0) + 1, baseline.get(recipient, 0) + source_count + 1)
            )
            assert {row.canonical_event_id for row in rows} == {event.id for event in events}
            head = await session.get(ChangeHeadRecord, recipient)
            assert head is not None
            assert head.next_sequence == baseline.get(recipient, 0) + source_count + 1


async def test_sql_failure_after_publication_rolls_back_heads_journal_and_outbox_markers(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    await owned.send()(owned.command())
    await stage(owned, await message_events(owned))
    async with owned.api.sessions() as session:
        pending_count = len(tuple(await session.scalars(select(ChangeOutboxRecord))))
    uow = SqlChangePublicationUnitOfWork(owned.api.sessions)

    async def failed_publication() -> None:
        async with uow.transaction() as transaction:
            hints = await transaction.claim_changes(PUBLICATION_BATCH_SIZE)
            await transaction.publish_changes(hints, await transaction.now())
            raise RuntimeError("Controlled failure after actual journal writes")

    with pytest.raises(RuntimeError, match="Controlled failure after actual journal writes"):
        await failed_publication()
    async with owned.api.sessions() as session:
        assert not tuple(await session.scalars(select(ChangeHeadRecord)))
        assert not tuple(await session.scalars(select(PublishedChangeRecord)))
        assert all(
            row.published_sequence is None
            for row in await session.scalars(select(ChangeOutboxRecord))
        )
    assert await PublishChanges(uow)() == pending_count


@dataclass(slots=True)
class StagingRecorder:
    fail: bool = True

    async def __call__(self, session: AsyncSession, operation: MessageOperation) -> None:
        await record_message_outcome(session, operation)
        event = (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.message_operation_id == operation.id
                )
            )
        ).one()
        await stage_change_outbox(session, event)
        if self.fail:
            raise RuntimeError("Controlled failure after actual outbox stage")


async def test_business_terminal_counter_canonical_and_staged_notifications_rollback_together(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    await drain(owned)
    async with owned.api.sessions() as session:
        original_outbox = frozenset(
            (row.canonical_event_id, row.recipient_id)
            for row in await session.scalars(select(ChangeOutboxRecord))
        )
    command = owned.command()
    recorder = StagingRecorder()
    send = SendMessage(SqlMessageUnitOfWork(owned.api.sessions, recorder), HASHER, FINGERPRINTER)
    with pytest.raises(RuntimeError, match="Controlled failure after actual outbox stage"):
        await send(command)
    async with owned.api.sessions() as session:
        assert not tuple(await session.scalars(select(MessageRecord)))
        assert (
            frozenset(
                (row.canonical_event_id, row.recipient_id)
                for row in await session.scalars(select(ChangeOutboxRecord))
            )
            == original_outbox
        )
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind.like("message.%"))
            )
        )
        conversation = await session.get(ConversationRecord, owned.conversation_id)
        assert conversation is not None
        assert conversation.next_message_sequence == 1
    recorder.fail = False
    assert (await send(command)).message is not None
    assert await PublishChanges(SqlChangePublicationUnitOfWork(owned.api.sessions))() == len(
        (owned.sender, owned.recipient)
    )


@pytest.mark.parametrize(
    "misuse", ["without_claim", "repeat_claim", "wrong_recipient", "republish", "empty_claim"]
)
async def test_publication_cannot_escape_or_reuse_its_actual_transaction_claim(
    identity_engine: AsyncEngine,
    misuse: str,
) -> None:
    from dataclasses import replace
    from uuid import uuid4

    owned = await chat(identity_engine)
    await drain(owned)
    baseline = await head_positions(owned)
    if misuse != "empty_claim":
        await owned.send()(owned.command())
    uow = SqlChangePublicationUnitOfWork(owned.api.sessions)

    async def misuse_claim() -> None:
        async with uow.transaction() as transaction:
            if misuse == "without_claim":
                await transaction.publish_changes((), await transaction.now())
                return
            hints = await transaction.claim_changes(PUBLICATION_BATCH_SIZE)
            if misuse == "repeat_claim":
                await transaction.claim_changes(PUBLICATION_BATCH_SIZE)
            elif misuse == "wrong_recipient":
                await transaction.publish_changes(
                    (replace(hints[0], recipient_id=uuid4()), *hints[1:]), await transaction.now()
                )
            else:
                await transaction.publish_changes(hints, await transaction.now())
                await transaction.publish_changes(hints, await transaction.now())

    with pytest.raises(RuntimeError, match=r"Publication|Empty"):
        await misuse_claim()
    assert await head_positions(owned) == baseline
    publisher = PublishChanges(uow)
    assert await publisher() == (
        0 if misuse == "empty_claim" else len((owned.sender, owned.recipient))
    )


async def test_counter_exhaustion_rolls_back_all_recipients_without_partial_delivery(
    identity_engine: AsyncEngine,
) -> None:
    from sqlalchemy import update

    from studymate.domain.changes import MAX_DELIVERY_SEQUENCE

    owned = await chat(identity_engine)
    await drain(owned)
    async with owned.api.sessions.begin() as session:
        await session.execute(
            delete(PublishedChangeRecord).where(
                PublishedChangeRecord.recipient_id == owned.sender.id
            )
        )
        await session.execute(
            update(ChangeHeadRecord)
            .where(ChangeHeadRecord.recipient_id == owned.sender.id)
            .values(
                next_sequence=MAX_DELIVERY_SEQUENCE,
                expired_through_sequence=MAX_DELIVERY_SEQUENCE - 1,
            )
        )
    baseline = await head_positions(owned)
    await owned.send()(owned.command())
    with pytest.raises(RuntimeError, match="sequence is exhausted"):
        await PublishChanges(SqlChangePublicationUnitOfWork(owned.api.sessions))()
    assert await head_positions(owned) == baseline
    async with owned.api.sessions() as session:
        pending = tuple(
            await session.scalars(
                select(ChangeOutboxRecord).where(ChangeOutboxRecord.published_sequence.is_(None))
            )
        )
        assert len(pending) == len((owned.sender, owned.recipient))
