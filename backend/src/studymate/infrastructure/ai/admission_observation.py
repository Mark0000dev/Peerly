"""One fresh factual observation after the actual canonical slot lock is held."""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import DateTime, Nullable, and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from studymate.application.ai.ports import Admission, AiUnavailableError
from studymate.domain.ai.tasks import AiKind, kind_of
from studymate.infrastructure.ai.models import (
    AiBudgetRecord,
    AiIntentRecord,
    AiJobRecord,
    AiSlotRecord,
)


@dataclass(frozen=True, slots=True)
class ObservedBudget:
    tokens: float
    refilled_at: datetime


@dataclass(frozen=True, slots=True)
class AdmissionObservation:
    at: datetime
    slot: AiSlotRecord = field(repr=False)
    prior_digest: bytes | None = field(repr=False)
    prior_job: AiJobRecord | None = field(repr=False)
    matching: AiJobRecord | None = field(repr=False)
    expired: int
    queued: int
    interactive: int
    outstanding: int
    budget: ObservedBudget | None = field(repr=False)


async def observe_admission(session: AsyncSession, intent: Admission) -> AdmissionObservation:
    clock = (
        select(func.clock_timestamp(type_=DateTime(timezone=True)).label("at"))
        .cte("student_admission_clock")
        .prefix_with("MATERIALIZED")
    )
    at = clock.c.at
    live_queued = and_(AiJobRecord.state == "queued", AiJobRecord.deadline > at)
    expired = (
        select(func.count())
        .select_from(AiJobRecord)
        .where(AiJobRecord.state == "queued", AiJobRecord.deadline <= at)
        .correlate(clock)
        .scalar_subquery()
    )
    queued = (
        select(func.count())
        .select_from(AiJobRecord)
        .where(live_queued)
        .correlate(clock)
        .scalar_subquery()
    )
    interactive = (
        select(func.count())
        .select_from(AiJobRecord)
        .where(live_queued, AiJobRecord.kind != AiKind.TRIAGE_REPORT.value)
        .correlate(clock)
        .scalar_subquery()
    )
    outstanding = (
        select(func.count())
        .select_from(AiJobRecord)
        .where(
            AiJobRecord.actor_id == intent.actor_id,
            or_(live_queued, AiJobRecord.state == "running"),
        )
        .correlate(clock)
        .scalar_subquery()
    )
    matching = aliased(
        AiJobRecord,
        select(AiJobRecord)
        .join(clock, true())
        .where(
            AiJobRecord.actor_id == intent.actor_id,
            AiJobRecord.kind == kind_of(intent.task).value,
            AiJobRecord.digest == intent.digest,
            AiJobRecord.state.in_(("queued", "running")),
            AiJobRecord.deadline > at,
        )
        .order_by(AiJobRecord.created_at)
        .limit(1)
        .subquery(),
    )
    prior = aliased(AiJobRecord)
    row = (
        await session.execute(
            select(
                at,
                AiSlotRecord,
                Nullable(AiIntentRecord.digest),
                Nullable(prior),
                Nullable(matching),
                expired,
                queued,
                interactive,
                outstanding,
                Nullable(AiBudgetRecord.actor_id),
                Nullable(AiBudgetRecord.tokens),
                Nullable(AiBudgetRecord.refilled_at),
            )
            .select_from(clock)
            .join(AiSlotRecord, AiSlotRecord.id == 1)
            .outerjoin(
                AiIntentRecord,
                and_(
                    AiIntentRecord.actor_id == intent.actor_id,
                    AiIntentRecord.kind == kind_of(intent.task).value,
                    AiIntentRecord.key == intent.key.value,
                ),
            )
            .outerjoin(
                prior,
                and_(
                    prior.id == AiIntentRecord.job_id,
                    prior.actor_id == intent.actor_id,
                    prior.kind != AiKind.TRIAGE_REPORT.value,
                ),
            )
            .outerjoin(matching, true())
            .outerjoin(AiBudgetRecord, AiBudgetRecord.actor_id == intent.actor_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        raise AiUnavailableError
    (
        sampled_at,
        slot,
        prior_digest,
        prior_job,
        match,
        expired_count,
        queue_count,
        interactive_count,
        actor_count,
        budget_actor,
        budget_tokens,
        budget_refilled,
    ) = row
    budget = None
    if budget_actor is not None:
        if budget_tokens is None or budget_refilled is None:
            raise RuntimeError("Observed actor budget lost its actual stored token/refill facts")
        budget = ObservedBudget(budget_tokens, budget_refilled)
    return AdmissionObservation(
        sampled_at,
        slot,
        prior_digest,
        prior_job,
        match,
        expired_count,
        queue_count,
        interactive_count,
        actor_count,
        budget,
    )
