from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.changes.retention import PruneChanges
from studymate.infrastructure.changes.models import (
    ChangeOutboxRecord,
    PublishedChangeRecord,
)
from studymate.infrastructure.changes.retention import SqlChangeRetentionUnitOfWork
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from tests.integration.change_fixture import drain, head_positions
from tests.integration.migrations import run_revision_step
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("state", ["pending", "published", "pruned"])
async def test_full_downgrade_preserves_delivery_markers_and_business_sources(
    identity_engine: AsyncEngine,
    state: str,
) -> None:
    owned = await chat(identity_engine)
    await owned.send()(owned.command())
    if state != "pending":
        await drain(owned)
    if state == "pruned":
        async with owned.api.sessions.begin() as session:
            await session.execute(
                update(PublishedChangeRecord).values(
                    published_at=func.clock_timestamp() - timedelta(days=2)
                )
            )
        assert await PruneChanges(SqlChangeRetentionUnitOfWork(owned.api.sessions))() > 0
    heads_before = await head_positions(owned)
    async with owned.api.sessions() as session:
        events_before = frozenset(await session.scalars(select(ProductEventRecord.id)))
        messages_before = frozenset(await session.scalars(select(MessageRecord.id)))
        markers_before = frozenset(
            (
                await session.execute(
                    select(ChangeOutboxRecord.canonical_event_id, ChangeOutboxRecord.recipient_id)
                )
            ).all()
        )
        assert markers_before
        if state == "pruned":
            assert (
                await session.scalar(select(func.count()).select_from(PublishedChangeRecord)) == 0
            )

    def downgrade(connection: Connection) -> None:
        configuration = Config("alembic.ini")
        configuration.attributes["connection"] = connection
        command.downgrade(configuration, "0035_conversation_list_indexes")

    # The current full chain first protects newer canonical revision sources.
    # Exercise the original delivery guard separately without changing the head.
    with pytest.raises(RuntimeError, match="pending or published change delivery history"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(run_revision_step, "0036_change_delivery", "downgrade")
    with pytest.raises(RuntimeError, match="Refusing to drop retained academic revision events"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(downgrade)
    assert await head_positions(owned) == heads_before
    async with owned.api.sessions() as session:
        assert frozenset(await session.scalars(select(ProductEventRecord.id))) == events_before
        assert frozenset(await session.scalars(select(MessageRecord.id))) == messages_before
        assert (
            frozenset(
                (
                    await session.execute(
                        select(
                            ChangeOutboxRecord.canonical_event_id, ChangeOutboxRecord.recipient_id
                        )
                    )
                ).all()
            )
            == markers_before
        )
