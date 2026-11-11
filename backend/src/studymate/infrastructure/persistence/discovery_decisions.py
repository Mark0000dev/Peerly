"""One actual actor-owned decision sequence shared by Pass and Request sends."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from studymate.infrastructure.persistence.discovery_pass_models import DiscoveryDecisionHeadRecord


async def advance_discovery_decision(session: AsyncSession, actor_id: UUID) -> int:
    """Caller holds the actor account lock; preview reads must never call this."""
    head = await session.get(DiscoveryDecisionHeadRecord, actor_id)
    if head is None:
        head = DiscoveryDecisionHeadRecord(account_id=actor_id, last_sequence=1)
        session.add(head)
    else:
        head.last_sequence += 1
    await session.flush()
    return head.last_sequence
