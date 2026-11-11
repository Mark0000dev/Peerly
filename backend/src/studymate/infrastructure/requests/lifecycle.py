"""Atomic lifecycle effects; caller already owns the relevant real account locks."""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.relationships import AccountPair
from studymate.domain.requests.states import ConnectionRequest
from studymate.infrastructure.persistence.block_models import RelationshipRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.requests.events import RequestOutcomeRecorder
from studymate.infrastructure.requests.models import ConnectionRequestRecord, RequestPreviewRecord
from studymate.infrastructure.requests.reads import read_request
from studymate.infrastructure.requests.writes import save_request


async def close_actor_requests(
    session: AsyncSession,
    account_id: UUID,
    initiator_id: UUID | None,
    recorder: RequestOutcomeRecorder,
) -> tuple[ConnectionRequest, ...]:
    """Caller holds affected account lock; NEVER acquire a lower peer lock here.

    Pair writers need that affected account before their relationship lock, so
    the lifecycle caller can close all owned pairs without reverse lock ordering.
    Administrative effects use None and preserve their separate actual audit.
    """
    ids = tuple(
        await session.scalars(
            select(RelationshipRecord.id)
            .join(
                ConnectionRequestRecord,
                ConnectionRequestRecord.relationship_id == RelationshipRecord.id,
            )
            .where(
                or_(
                    ConnectionRequestRecord.sender_id == account_id,
                    ConnectionRequestRecord.recipient_id == account_id,
                ),
                ConnectionRequestRecord.state.in_(("pending", "pending_decline")),
            )
        )
    )
    if not ids:
        return ()
    await session.execute(
        select(RelationshipRecord.id)
        .where(RelationshipRecord.id.in_(ids))
        .order_by(RelationshipRecord.id)
        .with_for_update()
    )
    records = tuple(
        await session.scalars(
            select(ConnectionRequestRecord.id)
            .where(
                ConnectionRequestRecord.relationship_id.in_(ids),
                ConnectionRequestRecord.state.in_(("pending", "pending_decline")),
            )
            .order_by(ConnectionRequestRecord.id)
            .with_for_update()
        )
    )
    return await close_locked_requests(session, records, initiator_id, recorder)


async def close_goal_requests(
    session: AsyncSession,
    account_id: UUID,
    goal_id: UUID,
    initiator_id: UUID | None,
    recorder: RequestOutcomeRecorder,
) -> tuple[ConnectionRequest, ...]:
    """Caller holds goal owner's account; no peer account locks are acquired.

    Match the actual owned retained goal ID, deliberately across all versions.
    Incoming offers use recipient_goal; accepted conversations remain untouched.
    """
    owned_source = or_(
        and_(
            RequestPreviewRecord.sender_id == account_id,
            RequestPreviewRecord.sender_goal_id == goal_id,
        ),
        and_(
            RequestPreviewRecord.recipient_id == account_id,
            RequestPreviewRecord.recipient_goal_id == goal_id,
        ),
    )
    pending = (
        select(ConnectionRequestRecord.id)
        .join(RequestPreviewRecord, RequestPreviewRecord.id == ConnectionRequestRecord.preview_id)
        .where(owned_source, ConnectionRequestRecord.state.in_(("pending", "pending_decline")))
    )
    relationships = tuple(
        await session.scalars(
            select(ConnectionRequestRecord.relationship_id).where(
                ConnectionRequestRecord.id.in_(pending)
            )
        )
    )
    if not relationships:
        return ()
    await session.execute(
        select(RelationshipRecord.id)
        .where(RelationshipRecord.id.in_(relationships))
        .order_by(RelationshipRecord.id)
        .with_for_update()
    )
    records = tuple(
        await session.scalars(
            pending.where(ConnectionRequestRecord.relationship_id.in_(relationships))
            .order_by(ConnectionRequestRecord.id)
            .with_for_update(of=ConnectionRequestRecord)
        )
    )
    return await close_locked_requests(session, records, initiator_id, recorder)


async def close_pair_requests(
    session: AsyncSession,
    pair: AccountPair,
    initiator_id: UUID | None,
    recorder: RequestOutcomeRecorder,
) -> tuple[ConnectionRequest, ...]:
    """Both sorted account locks already held by the actual block/contact writer."""
    relationship = await session.scalar(
        select(RelationshipRecord.id)
        .where(RelationshipRecord.low_id == pair.low, RelationshipRecord.high_id == pair.high)
        .with_for_update()
    )
    if relationship is None:
        return ()
    records = tuple(
        await session.scalars(
            select(ConnectionRequestRecord.id)
            .where(
                ConnectionRequestRecord.relationship_id == relationship,
                ConnectionRequestRecord.state.in_(("pending", "pending_decline")),
            )
            .order_by(ConnectionRequestRecord.id)
            .with_for_update()
        )
    )
    return await close_locked_requests(session, records, initiator_id, recorder)


async def close_locked_requests(
    session: AsyncSession,
    ids: tuple[UUID, ...],
    initiator_id: UUID | None,
    recorder: RequestOutcomeRecorder,
) -> tuple[ConnectionRequest, ...]:
    at = await SqlIdentityTransaction(session).now()
    changed = []
    for request_id in ids:
        current = await read_request(session, request_id)
        if current is None:
            raise RuntimeError("Locked lifecycle request disappeared")
        closed = current.close_unavailable(at)
        if closed != current:
            await save_request(session, closed, initiator_id, recorder)
            changed.append(closed)
    return tuple(changed)
