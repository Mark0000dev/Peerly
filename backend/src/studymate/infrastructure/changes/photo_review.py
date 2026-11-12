"""Content-free actual owner/pending-request invalidations; chats remain unaffected."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.changes import ChangeHint, ChangeResource
from studymate.infrastructure.operator.photo_review_models import OperatorPhotoReviewRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.models import ConnectionRequestRecord


async def photo_review_hints(
    session: AsyncSession, events: tuple[ProductEventRecord, ...]
) -> dict[UUID, tuple[ChangeHint, ...]]:
    selected = tuple(event for event in events if event.kind == "photo.reviewed")
    if not selected:
        return {}
    reviews = {
        row.id: row
        for row in await session.scalars(
            select(OperatorPhotoReviewRecord).where(
                OperatorPhotoReviewRecord.id.in_(tuple(event.photo_review_id for event in selected))
            )
        )
    }
    targets = tuple({source.account_id for source in reviews.values()})
    pending = tuple(
        await session.scalars(
            select(ConnectionRequestRecord).where(
                or_(
                    ConnectionRequestRecord.sender_id.in_(targets),
                    ConnectionRequestRecord.recipient_id.in_(targets),
                ),
                ConnectionRequestRecord.state.in_(("pending", "pending_decline")),
            )
        )
    )
    result: dict[UUID, tuple[ChangeHint, ...]] = {}
    for event in selected:
        source = reviews.get(event.photo_review_id) if event.photo_review_id is not None else None
        if (
            source is None
            or source.operator_id != event.account_id
            or source.version != event.photo_review_version
        ):
            raise RuntimeError("Photo review hint lost its actual human source proof")
        hints = [
            ChangeHint(event.id, source.account_id, ChangeResource.ACCOUNT, source.account_id, None)
        ]
        for request in pending:
            if source.account_id not in (request.sender_id, request.recipient_id):
                continue
            peer = (
                request.recipient_id
                if request.sender_id == source.account_id
                else request.sender_id
            )
            hints.append(
                ChangeHint(
                    event.id, peer, ChangeResource.REQUEST, request.id, request.current_version
                )
            )
        result[event.id] = tuple(hints)
    return result
