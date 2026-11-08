from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from studymate.application.changes.publication import PublishChanges
from studymate.infrastructure.changes.models import ChangeHeadRecord
from studymate.infrastructure.changes.publication import SqlChangePublicationUnitOfWork
from studymate.infrastructure.changes.staging import stage_change_outbox
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from tests.integration.test_message_commands import Chat

FIXTURE_DRAIN_BATCHES = 10


async def message_events(owned: Chat) -> tuple[ProductEventRecord, ...]:
    async with owned.api.sessions() as session:
        return tuple(
            await session.scalars(
                select(ProductEventRecord)
                .where(ProductEventRecord.kind == "message.confirmed")
                .order_by(ProductEventRecord.occurred_at)
            )
        )


async def stage(owned: Chat, events: Sequence[ProductEventRecord]) -> None:
    async with owned.api.sessions.begin() as session:
        for event in events:
            await stage_change_outbox(session, event)


async def drain(owned: Chat) -> None:
    publish = PublishChanges(SqlChangePublicationUnitOfWork(owned.api.sessions))
    for _ in range(FIXTURE_DRAIN_BATCHES):
        if await publish() == 0:
            return
    raise AssertionError("Bounded fixture baseline failed to drain its finite committed sources")


async def head_positions(owned: Chat) -> dict[UUID, int]:
    async with owned.api.sessions() as session:
        return {
            row.recipient_id: row.next_sequence - 1
            for row in await session.scalars(select(ChangeHeadRecord))
        }
