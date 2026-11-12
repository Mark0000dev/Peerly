"""One row per actual immutable triage proof, without authority/evidence shortcuts."""

import hmac
from uuid import UUID

from sqlalchemy import DateTime, Nullable, Select, and_, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.operator.report_triage_ports import (
    StoredReportTriage,
    TriageIntentObservation,
)
from studymate.infrastructure.ai.models import AiIntentRecord, AiJobRecord
from studymate.infrastructure.ai.persistence import job_value
from studymate.infrastructure.operator.models import OperatorAccessRevisionRecord
from studymate.infrastructure.operator.report_triage_models import (
    ReportTriageEvidenceRecord,
    ReportTriageSubmissionRecord,
)
from studymate.infrastructure.operator.report_triage_values import (
    triage_snapshot_value,
    triage_submission_value,
)


def stored_statement() -> Select[
    ReportTriageSubmissionRecord,
    AiJobRecord | None,
    ReportTriageEvidenceRecord | None,
    OperatorAccessRevisionRecord | None,
]:
    proof, source, grant = (
        ReportTriageSubmissionRecord,
        ReportTriageEvidenceRecord,
        OperatorAccessRevisionRecord,
    )
    return (
        select(proof, Nullable(AiJobRecord), Nullable(source), Nullable(grant))
        .select_from(proof)
        .outerjoin(AiJobRecord, AiJobRecord.id == proof.job_id)
        .outerjoin(
            source,
            and_(source.report_id == proof.report_id, source.version == proof.source_version),
        )
        .outerjoin(
            grant,
            and_(
                grant.account_id == source.operator_id,
                grant.version == source.operator_access_version,
            ),
        )
    )


def stored_value(
    proof: ReportTriageSubmissionRecord,
    job: AiJobRecord | None,
    source: ReportTriageEvidenceRecord | None,
    grant: OperatorAccessRevisionRecord | None,
    report_id: UUID,
) -> StoredReportTriage:
    if (
        job is None
        or source is None
        or grant is None
        or proof.report_id != report_id
        or (job.actor_id, job.kind, job.source_id, job.source_version)
        != (proof.operator_id, "triage_report", proof.report_id, proof.source_version)
    ):
        raise RuntimeError("Actual triage proof lost its exact source/job/operator grant")
    snapshot = triage_snapshot_value(source, grant)
    return StoredReportTriage(job_value(job), snapshot, triage_submission_value(proof, snapshot))


async def read_triage_job(
    session: AsyncSession, job_id: UUID, report_id: UUID
) -> StoredReportTriage:
    row = (
        await session.execute(
            stored_statement().where(ReportTriageSubmissionRecord.job_id == job_id)
        )
    ).one_or_none()
    if row is None:
        raise RuntimeError("Actual triage job lacks its immutable submission proof")
    return stored_value(*row, report_id)


async def read_latest_triage(session: AsyncSession, report_id: UUID) -> StoredReportTriage | None:
    proof = ReportTriageSubmissionRecord
    row = (
        await session.execute(
            stored_statement()
            .where(proof.report_id == report_id)
            .order_by(proof.submitted_at.desc(), proof.job_id.desc())
            .limit(1)
        )
    ).one_or_none()
    return stored_value(*row, report_id) if row is not None else None


async def read_triage_intent(
    session: AsyncSession, actor_id: UUID, report_id: UUID, key: IntentKey, digest: bytes
) -> TriageIntentObservation:
    intent, proof, source, grant = (
        AiIntentRecord,
        ReportTriageSubmissionRecord,
        ReportTriageEvidenceRecord,
        OperatorAccessRevisionRecord,
    )
    one = select(literal(1).label("one")).subquery()
    row = (
        await session.execute(
            select(
                Nullable(intent),
                Nullable(proof),
                Nullable(AiJobRecord),
                Nullable(source),
                Nullable(grant),
                func.clock_timestamp(type_=DateTime(timezone=True)),
            )
            .select_from(one)
            .outerjoin(
                intent,
                and_(
                    intent.actor_id == actor_id,
                    intent.kind == "triage_report",
                    intent.key == key.value,
                ),
            )
            .outerjoin(proof, proof.job_id == intent.job_id)
            .outerjoin(AiJobRecord, AiJobRecord.id == intent.job_id)
            .outerjoin(
                source,
                and_(source.report_id == proof.report_id, source.version == proof.source_version),
            )
            .outerjoin(
                grant,
                and_(
                    grant.account_id == source.operator_id,
                    grant.version == source.operator_access_version,
                ),
            )
        )
    ).one()
    prior, submission, job, evidence, original_grant, at = row
    if prior is None:
        return TriageIntentObservation(None, at)
    if not hmac.compare_digest(prior.digest, digest):
        raise IdempotencyConflictError
    if submission is None:
        raise RuntimeError("Actual triage intent lacks its immutable proof")
    result = stored_value(submission, job, evidence, original_grant, report_id)
    if result.job.actor_id != actor_id:
        raise RuntimeError("Actual triage intent differs from its scoped actor")
    return TriageIntentObservation(result, at)
