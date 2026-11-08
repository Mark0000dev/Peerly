"""Safe aggregate invalidation for lifecycle removal from already cached student views.

Accounts are retained, so this recipient superset only grows. Publication consumes
only recipient references staged atomically with the original canonical outcome.
No target identity, lifecycle action or private reason is sent in these hints.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.changes import ChangeHint, ChangeResource
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord


async def lifecycle_hints(
    session: AsyncSession, events: tuple[ProductEventRecord, ...]
) -> dict[UUID, tuple[ChangeHint, ...]]:
    selected = tuple(event for event in events if event.kind == "account.lifecycle_changed")
    if not selected:
        return {}
    recipients = tuple(await session.scalars(select(AccountRecord.id).order_by(AccountRecord.id)))
    hints: dict[UUID, tuple[ChangeHint, ...]] = {}
    for event in selected:
        if (
            event.lifecycle_revision_id is None
            or event.lifecycle_account_id is None
            or event.lifecycle_version is None
            or event.lifecycle_operation not in {"ban", "unban", "delete"}
        ):
            raise RuntimeError("Lifecycle invalidation lost its actual retained canonical source")
        hints[event.id] = tuple(
            ChangeHint(event.id, recipient, ChangeResource.ACCOUNT, recipient, None)
            for recipient in recipients
        )
    return hints
