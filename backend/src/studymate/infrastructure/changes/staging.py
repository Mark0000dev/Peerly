"""Stage actual recipient references atomically; publication owns delivery sequences later."""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.infrastructure.changes.academic import eligible_academic_hints
from studymate.infrastructure.changes.models import ChangeOutboxRecord
from studymate.infrastructure.changes.sources import project_change_hints
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord


async def stage_change_outbox(session: AsyncSession, event: ProductEventRecord) -> None:
    hints = (await project_change_hints(session, (event,)))[event.id]
    hints = await eligible_academic_hints(session, event, hints)
    if not hints:
        return
    recipients = tuple(sorted({hint.recipient_id for hint in hints}))
    if len(recipients) != len(hints):
        raise RuntimeError("One canonical event cannot enqueue duplicate recipient invalidations")
    await session.execute(
        insert(ChangeOutboxRecord)
        .values(
            [
                {
                    "canonical_event_id": event.id,
                    "recipient_id": recipient,
                    "staged_at": func.clock_timestamp(),
                }
                for recipient in recipients
            ]
        )
        .on_conflict_do_nothing(
            index_elements=[
                ChangeOutboxRecord.canonical_event_id,
                ChangeOutboxRecord.recipient_id,
            ]
        )
    )
