from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.changes.publication import PublishChanges
from studymate.application.changes.reads import ReadChanges
from studymate.application.changes.retention import PruneChanges
from studymate.infrastructure.changes.models import (
    ChangeHeadRecord,
    ChangeOutboxRecord,
    PublishedChangeRecord,
)
from studymate.infrastructure.changes.publication import SqlChangePublicationUnitOfWork
from studymate.infrastructure.changes.reads import SqlChangeReadUnitOfWork
from studymate.infrastructure.changes.retention import SqlChangeRetentionUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from tests.integration.change_fixture import drain, head_positions, message_events, stage
from tests.integration.requests.fixture import HASHER
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration
SOURCE_COUNT = 3


async def populated(engine: AsyncEngine) -> tuple[Chat, dict[UUID, int]]:
    owned = await chat(engine)
    await drain(owned)
    baseline = await head_positions(owned)
    for _ in range(SOURCE_COUNT):
        await owned.send()(owned.command())
    await stage(owned, await message_events(owned))
    assert (
        await PublishChanges(SqlChangePublicationUnitOfWork(owned.api.sessions))()
        == SOURCE_COUNT * 2
    )
    return owned, baseline


async def age(owned: Chat, sequences: tuple[int, ...], baseline: dict[UUID, int]) -> datetime:
    async with owned.api.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        old = now - timedelta(hours=25)
        for model, column in (
            (PublishedChangeRecord, PublishedChangeRecord.sequence),
            (ChangeOutboxRecord, ChangeOutboxRecord.published_sequence),
        ):
            clauses = tuple(
                and_(
                    model.recipient_id == recipient,
                    or_(
                        column <= baseline.get(recipient, 0),
                        column.in_(
                            tuple(baseline.get(recipient, 0) + sequence for sequence in sequences)
                        ),
                    ),
                )
                for recipient in (owned.sender.id, owned.recipient.id)
            )
            await session.execute(update(model).where(or_(*clauses)).values(published_at=old))
    return now


async def test_retention_only_prunes_old_contiguous_prefix_even_after_publication_clock_regression(
    identity_engine: AsyncEngine,
) -> None:
    owned, baseline = await populated(identity_engine)
    await age(owned, (1, SOURCE_COUNT), baseline)
    pruning = PruneChanges(SqlChangeRetentionUnitOfWork(owned.api.sessions))
    assert await pruning() == sum(baseline.values()) + len((owned.sender, owned.recipient))
    reader = ReadChanges(SqlChangeReadUnitOfWork(owned.api.sessions), HASHER)
    reset = await reader(owned.recipient.credential, 0)
    assert reset.reset_required
    assert reset.after_sequence == baseline.get(owned.recipient.id, 0) + SOURCE_COUNT
    retained = await reader(owned.recipient.credential, baseline.get(owned.recipient.id, 0) + 1)
    assert tuple(item.sequence for item in retained.changes) == (
        baseline.get(owned.recipient.id, 0) + 2,
        baseline.get(owned.recipient.id, 0) + SOURCE_COUNT,
    )
    assert not retained.reset_required
    assert await pruning() == 0
    await age(owned, (2,), baseline)
    assert await pruning() == len((owned.sender, owned.recipient)) * 2
    idle = await reader(
        owned.recipient.credential, baseline.get(owned.recipient.id, 0) + SOURCE_COUNT
    )
    assert not idle.reset_required
    assert not idle.changes
    async with owned.api.sessions() as session:
        assert not tuple(await session.scalars(select(PublishedChangeRecord)))
        assert (
            len(tuple(await session.scalars(select(ChangeOutboxRecord))))
            == sum(baseline.values()) + SOURCE_COUNT * 2
        )
        assert tuple(await session.scalars(select(ProductEventRecord)))
        assert all(
            row.expired_through_sequence == baseline.get(row.recipient_id, 0) + SOURCE_COUNT
            for row in await session.scalars(select(ChangeHeadRecord))
        )
    await stage(owned, await message_events(owned))
    publisher = PublishChanges(SqlChangePublicationUnitOfWork(owned.api.sessions))
    assert await publisher() == 0
    await owned.send()(owned.command())
    await stage(owned, await message_events(owned))
    assert await publisher() == len((owned.sender, owned.recipient))
    fresh = await reader(
        owned.recipient.credential, baseline.get(owned.recipient.id, 0) + SOURCE_COUNT
    )
    assert tuple(item.sequence for item in fresh.changes) == (
        baseline.get(owned.recipient.id, 0) + SOURCE_COUNT + 1,
    )


async def test_retention_delete_and_floor_rollback_together_without_losing_canonical_or_markers(
    identity_engine: AsyncEngine,
) -> None:
    owned, baseline = await populated(identity_engine)
    before = await age(owned, tuple(range(1, SOURCE_COUNT + 1)), baseline)
    uow = SqlChangeRetentionUnitOfWork(owned.api.sessions)

    async def fail_after_prune() -> None:
        async with uow.transaction() as transaction:
            assert await transaction.prune_changes(before, 1, 1) == 1
            raise RuntimeError("Controlled retention rollback")

    with pytest.raises(RuntimeError, match="Controlled retention rollback"):
        await fail_after_prune()
    async with owned.api.sessions() as session:
        assert (
            len(tuple(await session.scalars(select(PublishedChangeRecord))))
            == sum(baseline.values()) + SOURCE_COUNT * 2
        )
        assert all(
            row.expired_through_sequence == 0
            for row in await session.scalars(select(ChangeHeadRecord))
        )
    assert await PruneChanges(uow)() == sum(baseline.values()) + SOURCE_COUNT * 2


async def test_reader_sees_one_committed_floor_and_journal_while_pruning_is_uncommitted(
    identity_engine: AsyncEngine,
) -> None:
    owned, baseline = await populated(identity_engine)
    before = await age(owned, tuple(range(1, SOURCE_COUNT + 1)), baseline)
    reader = ReadChanges(SqlChangeReadUnitOfWork(owned.api.sessions), HASHER)
    async with SqlChangeRetentionUnitOfWork(owned.api.sessions).transaction() as transaction:
        assert await transaction.prune_changes(before, 2, SOURCE_COUNT) == SOURCE_COUNT * 2
        visible = await reader(owned.recipient.credential, 0)
        assert not visible.reset_required
        assert tuple(item.sequence for item in visible.changes) == tuple(
            range(1, baseline.get(owned.recipient.id, 0) + SOURCE_COUNT + 1)
        )
    assert (await reader(owned.recipient.credential, 0)).reset_required


async def test_idle_retention_does_not_create_fake_heads_or_modify_canonical_history(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    async with owned.api.sessions() as session:
        before = frozenset(await session.scalars(select(ProductEventRecord.id)))
    assert await PruneChanges(SqlChangeRetentionUnitOfWork(owned.api.sessions))() == 0
    async with owned.api.sessions() as session:
        assert not tuple(await session.scalars(select(ChangeHeadRecord)))
        assert frozenset(await session.scalars(select(ProductEventRecord.id))) == before
