import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.ai.policy import AdmissionPolicy
from studymate.application.ai.ports import AiUnavailableError, StudentSubmission
from studymate.application.ai.student import SubmitStudentJob
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError
from studymate.application.operator.report_triage import EnqueueReportTriage
from studymate.application.operator.report_triage_ports import ReportTriageSourceUnavailableError
from studymate.application.report_moderation.review import ReviewReport, ReviewReportCommand
from studymate.domain.ai.tasks import AiKind, Source
from studymate.domain.operator.report_triage import ReportTriageSubmission
from studymate.domain.report_moderation.reviews import ReportReviewAction, ReportReviewReason
from studymate.infrastructure.ai.models import AiIntentRecord, AiJobRecord
from studymate.infrastructure.ai.persistence import SqlAiUnitOfWork
from studymate.infrastructure.operator.report_triage_models import (
    ReportTriageEvidenceRecord,
    ReportTriageSubmissionRecord,
)
from studymate.infrastructure.operator.report_triage_transactions import (
    SqlOperatorReportTriageUnitOfWork,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import (
    record_operator_audit,
    record_report_review_event,
    record_report_triage_submission,
)
from studymate.infrastructure.report_moderation.transactions import SqlReportModerationUnitOfWork
from tests.integration.operator.report_triage.fixture import CODEC, prepared
from tests.integration.requests.fixture import FINGERPRINTER, HASHER

pytestmark = pytest.mark.integration


async def test_real_internal_admission_is_actor_proven_and_student_guard_is_unchanged(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    request = await api.command()
    result = await api.enqueue()(request)
    assert await api.enqueue()(request) == result
    assert result.observation.state.value == "queued"
    assert result.observation.priority is None
    async with api.unit.sessions() as session:
        source = (await session.scalars(select(ReportTriageEvidenceRecord))).one()
        proof = (await session.scalars(select(ReportTriageSubmissionRecord))).one()
        job = (await session.scalars(select(AiJobRecord))).one()
        assert source.operator_id == api.reports.owner.id
        assert source.actor_session_id == proof.actor_session_id
        assert proof.job_id == job.id == result.observation.job_id
        assert (job.source_id, job.source_version) == (source.report_id, source.version)
        assert job.kind == "triage_report"
        assert source.review_version is None
        event = await session.get(ProductEventRecord, proof.event_id)
        assert event is not None
        assert event.kind == "triage.submitted"
        assert event.account_id == api.reports.owner.id
        assert event.occurrence_key == result.submission.occurrence_key
        assert event.occurred_at == proof.submitted_at
        assert len(tuple(await session.scalars(select(AiIntentRecord)))) == 1
    with pytest.raises(StudentActionDeniedError):
        await SubmitStudentJob(SqlAiUnitOfWork(api.unit.sessions), HASHER, FINGERPRINTER)(
            api.reports.owner.credential,
            StudentSubmission(AiKind.CLARIFY_GOAL, Source(uuid4(), 1), "Explicit student goal"),
            IntentKey("ordinary-student-path"),
        )


async def test_actual_human_review_invalidates_new_triage_source_without_a_job(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    request = await api.command()
    await ReviewReport(
        SqlReportModerationUnitOfWork(
            api.unit.sessions, record_operator_audit, record_report_review_event
        ),
        HASHER,
        FINGERPRINTER,
    )(
        ReviewReportCommand(
            api.reports.owner.credential,
            api.reports.report.id,
            0,
            ReportReviewAction.ESCALATE,
            ReportReviewReason("human reviewed"),
            IntentKey("human-review-before-ai"),
        )
    )
    with pytest.raises(ReportTriageSourceUnavailableError):
        await api.enqueue()(request)
    async with api.unit.sessions() as session:
        assert tuple(await session.scalars(select(AiJobRecord))) == ()
        assert tuple(await session.scalars(select(ReportTriageEvidenceRecord))) == ()
        assert tuple(await session.scalars(select(ReportTriageSubmissionRecord))) == ()


async def test_concurrent_exact_actor_key_commits_one_snapshot_job_and_proof(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    request = await api.command()
    first, second = await asyncio.gather(api.enqueue()(request), api.enqueue()(request))
    assert first == second
    async with api.unit.sessions() as session:
        assert len(tuple(await session.scalars(select(AiJobRecord)))) == 1
        assert len(tuple(await session.scalars(select(ReportTriageEvidenceRecord)))) == 1
        assert len(tuple(await session.scalars(select(ReportTriageSubmissionRecord)))) == 1


async def fail_canonical(session: AsyncSession, source: ReportTriageSubmission) -> None:
    await record_report_triage_submission(session, source)
    raise RuntimeError("synthetic triage canonical failure")


async def test_actual_canonical_failure_rolls_back_native_job_intent_snapshot_and_proof(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    request = await api.command()
    unit = SqlOperatorReportTriageUnitOfWork(
        api.unit.sessions, record_operator_audit, fail_canonical
    )
    with pytest.raises(RuntimeError, match="synthetic triage canonical failure"):
        await EnqueueReportTriage(unit, HASHER, FINGERPRINTER, CODEC)(request)
    async with api.unit.sessions() as session:
        assert tuple(await session.scalars(select(AiJobRecord))) == ()
        assert tuple(await session.scalars(select(AiIntentRecord))) == ()
        assert tuple(await session.scalars(select(ReportTriageEvidenceRecord))) == ()
        assert tuple(await session.scalars(select(ReportTriageSubmissionRecord))) == ()
        assert (
            tuple(
                await session.scalars(
                    select(ProductEventRecord).where(ProductEventRecord.kind == "triage.submitted")
                )
            )
            == ()
        )


async def test_actual_queue_full_does_not_persist_second_snapshot_or_fake_pending_job(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    limited = replace(api.unit, policy=AdmissionPolicy(queue_limit=1, internal_reserve=0))
    enqueue = EnqueueReportTriage(limited, HASHER, FINGERPRINTER, CODEC)
    await enqueue(await api.command())
    await ReviewReport(
        SqlReportModerationUnitOfWork(
            api.unit.sessions, record_operator_audit, record_report_review_event
        ),
        HASHER,
        FINGERPRINTER,
    )(
        ReviewReportCommand(
            api.reports.owner.credential,
            api.reports.report.id,
            0,
            ReportReviewAction.DISMISS,
            ReportReviewReason("human decision"),
            IntentKey("human-review-queue-full"),
        )
    )
    with pytest.raises(AiUnavailableError):
        await enqueue(await api.command("second-triage-source"))
    async with api.unit.sessions() as session:
        assert len(tuple(await session.scalars(select(AiJobRecord)))) == 1
        assert len(tuple(await session.scalars(select(ReportTriageEvidenceRecord)))) == 1
        assert len(tuple(await session.scalars(select(ReportTriageSubmissionRecord)))) == 1
