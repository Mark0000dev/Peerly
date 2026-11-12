"""Capability-specific admission, existing slot/quotas/proofs and canonical producer."""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.ai.policy import AdmissionPolicy
from studymate.application.ai.ports import AiQuotaError, AiUnavailableError
from studymate.application.operator.report_triage_ports import (
    ReportTriageAdmission,
    StoredReportTriage,
)
from studymate.domain.ai.jobs import AiJob
from studymate.domain.operator.report_triage import ReportTriageSubmission
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.infrastructure.ai.models import AiIntentRecord, AiJobRecord, AiSlotRecord
from studymate.infrastructure.ai.persistence import job_value, terminal_event
from studymate.infrastructure.ai.runtime.availability import require_runtime_ready
from studymate.infrastructure.ai.runtime.health import REPORT_GUARD_VERSION
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.operator.report_triage_capacity import read_triage_capacity
from studymate.infrastructure.operator.report_triage_reads import read_triage_job
from studymate.infrastructure.operator.report_triage_writes import write_new_triage


async def admit_triage_submission(
    session: AsyncSession,
    policy: AdmissionPolicy,
    request: ReportTriageAdmission,
    recorder: Callable[[AsyncSession, ReportTriageSubmission], Awaitable[None]],
) -> StoredReportTriage:
    snapshot = request.source.snapshot
    slot = await session.scalar(
        select(AiSlotRecord)
        .where(AiSlotRecord.id == 1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if slot is None:
        raise AiUnavailableError
    capacity = await read_triage_capacity(session, snapshot.operator.account_id, request.digest)
    at = capacity.at
    versions = require_runtime_ready(slot, at)
    if at < snapshot.captured_at:
        raise RuntimeError("Triage admission clock precedes its actual captured source")
    if slot.runtime_report_guard_version != REPORT_GUARD_VERSION:
        raise AiUnavailableError
    if capacity.matching is not None:
        matched = job_value(capacity.matching)
        if matched.task != snapshot.task or matched.actor_id != snapshot.operator.account_id:
            raise RuntimeError("Actual matching triage job differs from its current locked source")
        await session.execute(
            insert(AiIntentRecord).values(
                actor_id=matched.actor_id,
                kind="triage_report",
                key=request.key.value,
                job_id=matched.id,
                digest=request.digest,
            )
        )
        return await read_triage_job(session, matched.id, snapshot.report.id)
    if capacity.expired:
        expired = tuple(
            await session.scalars(
                update(AiJobRecord)
                .where(AiJobRecord.state == "queued", AiJobRecord.deadline <= at)
                .values(state="expired")
                .returning(AiJobRecord)
            )
        )
        for record in expired:
            await terminal_event(session, record, at)
    if capacity.queued >= policy.queue_limit:
        raise AiUnavailableError
    if capacity.outstanding >= policy.student_outstanding:
        raise AiQuotaError
    available = (
        float(policy.bucket_capacity)
        if capacity.budget is None
        else min(
            float(policy.bucket_capacity),
            capacity.budget.tokens
            + max(0.0, (at - capacity.budget.refilled_at).total_seconds()) / policy.refill_seconds,
        )
    )
    if available < 1:
        raise AiQuotaError
    job = AiJob(
        uuid4(),
        snapshot.operator.account_id,
        snapshot.task,
        request.digest,
        versions,
        at,
        at + policy.internal_lifetime,
        at,
    )
    origin = current_origin()
    source = ReportTriageSubmission(
        job.id,
        snapshot.report.id,
        snapshot.version,
        snapshot.operator,
        snapshot.actor_session_id,
        at,
        request.event_id,
        OperatorEventOrigin(origin.request_id, origin.action_id, origin.trace_id, origin.span_id)
        if origin is not None
        else OperatorEventOrigin(),
    )
    await write_new_triage(session, request, job, source, available - 1)
    await recorder(session, source)
    return StoredReportTriage(job, snapshot, source)
