"""Dependency-ordered actual triage rows; the injected canonical recorder follows in-UoW."""

from sqlalchemy import literal, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.operator.report_triage_ports import (
    PreparedReportTriageSource,
    ReportTriageAdmission,
)
from studymate.domain.ai.jobs import AiJob
from studymate.domain.operator.report_triage import ReportTriageSubmission
from studymate.infrastructure.ai.codec import TASK_CODEC
from studymate.infrastructure.ai.models import AiBudgetRecord, AiIntentRecord, AiJobRecord
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.operator.report_triage_models import (
    ReportTriageEvidenceRecord,
    ReportTriageSubmissionRecord,
)


def evidence_values(source: PreparedReportTriageSource) -> dict[str, object]:
    snapshot = source.snapshot
    profile = snapshot.report.kind.value == "profile"
    return {
        "report_id": snapshot.report.id,
        "version": snapshot.version,
        "previous_version": snapshot.previous_version,
        "review_version": snapshot.review_version,
        "report_kind": snapshot.report.kind.value,
        "reporter_id": snapshot.report.reporter_id,
        "target_id": snapshot.report.target_id,
        "profile_context_id": snapshot.report.context_id if profile else None,
        "message_context_id": None if profile else snapshot.report.context_id,
        "operator_id": snapshot.operator.account_id,
        "operator_access_version": snapshot.operator.version,
        "operator_access_active": snapshot.operator.active,
        "actor_session_id": snapshot.actor_session_id,
        "evidence": snapshot.evidence,
        "evidence_digest": snapshot.evidence_digest,
        "captured_at": snapshot.captured_at,
    }


def job_values(job: AiJob) -> dict[str, object]:
    origin = current_origin()
    return {
        "id": job.id,
        "actor_id": job.actor_id,
        "kind": "triage_report",
        "source_id": job.task.source.id,
        "source_version": job.task.source.version,
        "digest": job.digest,
        "input_json": TASK_CODEC.dump_json(job.task).decode(),
        "model": job.versions.model,
        "prompt": job.versions.prompt,
        "schema_version": job.versions.schema,
        "adapter": job.versions.adapter,
        "state": job.state.value,
        "created_at": job.created_at,
        "deadline": job.deadline,
        "not_before": job.not_before,
        "attempts": job.attempts,
        "generation": job.generation,
        "request_id": origin.request_id if origin is not None else None,
        "action_id": origin.action_id if origin is not None else None,
        "trace_id": origin.trace_id if origin is not None else None,
        "span_id": origin.span_id if origin is not None else None,
    }


async def write_new_triage(
    session: AsyncSession,
    request: ReportTriageAdmission,
    job: AiJob,
    submission: ReportTriageSubmission,
    remaining_tokens: float,
) -> None:
    source, intent_key, refilled_at = request.source, request.key.value, job.created_at
    snapshot = source.snapshot
    if source.exists:
        retained = (
            select(ReportTriageEvidenceRecord.report_id, ReportTriageEvidenceRecord.version)
            .where(
                ReportTriageEvidenceRecord.report_id == snapshot.report.id,
                ReportTriageEvidenceRecord.version == snapshot.version,
            )
            .cte("triage_source")
        )
    else:
        retained = (
            insert(ReportTriageEvidenceRecord)
            .values(**evidence_values(source))
            .returning(ReportTriageEvidenceRecord.report_id, ReportTriageEvidenceRecord.version)
            .cte("triage_source")
        )
    budget_insert = insert(AiBudgetRecord).values(
        actor_id=job.actor_id, tokens=remaining_tokens, refilled_at=refilled_at, last_served=0
    )
    budget = (
        budget_insert.on_conflict_do_update(
            index_elements=[AiBudgetRecord.actor_id],
            set_={"tokens": remaining_tokens, "refilled_at": refilled_at},
        )
        .returning(AiBudgetRecord.actor_id)
        .cte("triage_budget")
    )
    values = job_values(job)
    job_write = (
        insert(AiJobRecord)
        .from_select(
            list(values),
            select(*(literal(value) for value in values.values())).select_from(
                retained.join(budget, true())
            ),
        )
        .returning(AiJobRecord.id)
        .cte("triage_job")
    )
    intent = (
        insert(AiIntentRecord)
        .from_select(
            ["actor_id", "kind", "key", "job_id", "digest"],
            select(
                literal(job.actor_id),
                literal("triage_report"),
                literal(intent_key),
                job_write.c.id,
                literal(job.digest),
            ),
        )
        .returning(AiIntentRecord.job_id)
        .cte("triage_intent")
    )
    proof_values = {
        "report_id": submission.report_id,
        "source_version": submission.source_version,
        "operator_id": submission.operator.account_id,
        "operator_access_version": submission.operator.version,
        "operator_access_active": submission.operator.active,
        "actor_session_id": submission.actor_session_id,
        "kind": "triage_report",
        "submitted_at": submission.submitted_at,
        "event_id": submission.event_id,
        "event_kind": "triage.submitted",
        "http_request_id": submission.origin.http_request_id,
        "action_id": submission.origin.action_id,
        "trace_id": submission.origin.trace_id,
        "span_id": submission.origin.span_id,
    }
    proof = (
        insert(ReportTriageSubmissionRecord)
        .from_select(
            ["job_id", *proof_values],
            select(
                job_write.c.id, *(literal(value) for value in proof_values.values())
            ).select_from(job_write),
        )
        .returning(ReportTriageSubmissionRecord.job_id)
        .cte("triage_proof")
    )
    written = await session.scalar(select(proof.c.job_id).add_cte(intent))
    if written != job.id:
        raise RuntimeError("Atomic triage write did not return its actual new job/proof")
