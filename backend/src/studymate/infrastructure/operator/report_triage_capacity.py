"""One aggregate observation while the canonical slot and actor locks are held."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Nullable, and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from studymate.infrastructure.ai.models import AiBudgetRecord, AiJobRecord


@dataclass(frozen=True, slots=True)
class TriageCapacity:
    at: datetime
    expired: int
    queued: int
    outstanding: int
    budget: AiBudgetRecord | None
    matching: AiJobRecord | None


async def read_triage_capacity(
    session: AsyncSession, actor_id: UUID, digest: bytes
) -> TriageCapacity:
    clock = (
        select(func.clock_timestamp(type_=DateTime(timezone=True)).label("at"))
        .cte("triage_admission_clock")
        .prefix_with("MATERIALIZED")
    )
    at = clock.c.at
    live_queued = and_(AiJobRecord.state == "queued", AiJobRecord.deadline > at)
    queued = (
        select(func.count())
        .select_from(AiJobRecord)
        .where(live_queued)
        .correlate(clock)
        .scalar_subquery()
    )
    expired = (
        select(func.count())
        .select_from(AiJobRecord)
        .where(AiJobRecord.state == "queued", AiJobRecord.deadline <= at)
        .correlate(clock)
        .scalar_subquery()
    )
    outstanding = (
        select(func.count())
        .select_from(AiJobRecord)
        .where(AiJobRecord.actor_id == actor_id, or_(live_queued, AiJobRecord.state == "running"))
        .correlate(clock)
        .scalar_subquery()
    )
    matching = aliased(
        AiJobRecord,
        select(AiJobRecord)
        .select_from(AiJobRecord)
        .join(clock, true())
        .where(
            AiJobRecord.actor_id == actor_id,
            AiJobRecord.kind == "triage_report",
            AiJobRecord.digest == digest,
            AiJobRecord.state.in_(("queued", "running")),
            AiJobRecord.deadline > at,
        )
        .order_by(AiJobRecord.created_at)
        .limit(1)
        .subquery(),
    )
    row = (
        await session.execute(
            select(at, expired, queued, outstanding, Nullable(AiBudgetRecord), Nullable(matching))
            .select_from(clock)
            .outerjoin(AiBudgetRecord, AiBudgetRecord.actor_id == actor_id)
            .outerjoin(matching, true())
        )
    ).one()
    sampled_at, expired_count, count, actor_count, budget, match = row
    return TriageCapacity(sampled_at, expired_count, count, actor_count, budget, match)
