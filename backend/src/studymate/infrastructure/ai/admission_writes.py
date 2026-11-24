"""Dependency-ordered budget/job/intent writes in the existing admission transaction."""

from sqlalchemy import literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.idempotency import IntentKey
from studymate.infrastructure.ai.models import AiBudgetRecord, AiIntentRecord, AiJobRecord


def job_values(record: AiJobRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "actor_id": record.actor_id,
        "kind": record.kind,
        "source_id": record.source_id,
        "source_version": record.source_version,
        "digest": record.digest,
        "input_json": record.input_json,
        "model": record.model,
        "prompt": record.prompt,
        "schema_version": record.schema_version,
        "adapter": record.adapter,
        "state": record.state,
        "created_at": record.created_at,
        "deadline": record.deadline,
        "not_before": record.not_before,
        "attempts": record.attempts,
        "generation": record.generation,
        "request_id": record.request_id,
        "action_id": record.action_id,
        "trace_id": record.trace_id,
        "span_id": record.span_id,
    }


async def insert_admission(
    session: AsyncSession,
    record: AiJobRecord,
    key: IntentKey,
    balance: float,
    budget_existed: bool,
) -> None:
    at = record.created_at  # Budget and job share the same fresh admission clock.
    if budget_existed:
        budget = (
            update(AiBudgetRecord)
            .where(AiBudgetRecord.actor_id == record.actor_id)
            .values(tokens=balance, refilled_at=at)
            .returning(AiBudgetRecord.actor_id)
            .cte("student_budget")
        )
    else:
        budget = (
            insert(AiBudgetRecord)
            .values(actor_id=record.actor_id, tokens=balance, refilled_at=at, last_served=0)
            .returning(AiBudgetRecord.actor_id)
            .cte("student_budget")
        )
    values = job_values(record)
    job = (
        insert(AiJobRecord)
        .from_select(
            list(values), select(*(literal(value) for value in values.values())).select_from(budget)
        )
        .returning(AiJobRecord.id)
        .cte("student_job")
    )
    intent = (
        insert(AiIntentRecord)
        .from_select(
            ["actor_id", "kind", "key", "job_id", "digest"],
            select(
                literal(record.actor_id),
                literal(record.kind),
                literal(key.value),
                job.c.id,
                literal(record.digest),
            ).select_from(job),
        )
        .returning(AiIntentRecord.job_id)
    )
    written = await session.scalar(intent)
    if written != record.id:
        raise RuntimeError("Atomic student admission did not return its actual job/intent")
