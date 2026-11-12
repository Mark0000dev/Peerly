from uuid import uuid4

import pytest
from sqlalchemy import DateTime, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.ai.worker import ExecuteNextJob
from studymate.application.idempotency import IntentKey
from studymate.application.operator.report_triage import ReadReportTriage
from studymate.application.report_moderation.review import ReviewReport, ReviewReportCommand
from studymate.domain.ai.jobs import Failure, JobState
from studymate.domain.ai.tasks import Priority, ReportTriage
from studymate.domain.report_moderation.reviews import ReportReviewAction, ReportReviewReason
from studymate.infrastructure.ai.models import AiJobRecord
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
)
from studymate.infrastructure.persistence.product_events import (
    record_operator_audit,
    record_report_review_event,
)
from studymate.infrastructure.report_moderation.models import ReportReviewRevisionRecord
from studymate.infrastructure.report_moderation.transactions import SqlReportModerationUnitOfWork
from tests.integration.identity_recreation.fixtures import fresh_account, google_claim
from tests.integration.operator.report_triage.composition_test import ControlledReportExecutor
from tests.integration.operator.report_triage.fixture import TriageCase, prepared
from tests.integration.requests.fixture import FINGERPRINTER, HASHER

pytestmark = pytest.mark.integration


async def human_review(api: TriageCase) -> None:
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
            ReportReviewReason("actual later human review"),
            IntentKey(str(uuid4())),
        )
    )


async def revoke_grant(api: TriageCase) -> None:
    async with api.unit.sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        session.add(
            OperatorAccessRevisionRecord(
                account_id=api.reports.owner.id, version=2, active=False, changed_at=at
            )
        )
        await session.flush()
        await session.execute(
            update(OperatorAccessRecord)
            .where(OperatorAccessRecord.account_id == api.reports.owner.id)
            .values(current_version=2)
        )


@pytest.mark.parametrize("stage", ["claim", "finalize"])
async def test_actual_worker_rechecks_changed_review_source_before_advice_can_commit(
    ai_engine: AsyncEngine,
    triage_queue: SqlAiQueue,
    stage: str,
) -> None:
    api = await prepared(ai_engine)
    submitted = await api.enqueue()(await api.command())
    queue = triage_queue
    claimed = await queue.claim() if stage == "finalize" else None
    if stage == "finalize":
        assert claimed is not None
    await human_review(api)
    if claimed is None:
        assert await queue.claim() is None
    else:
        terminal = await queue.complete(
            claimed, ReportTriage(Priority.HIGH, "Controlled advisory"), stopped=True
        )
        assert terminal.failure == Failure.STALE_SOURCE
        assert terminal.result is None
    async with api.unit.sessions() as session:
        job = await session.get(AiJobRecord, submitted.observation.job_id)
        assert job is not None
        assert job.state == "failed"
        assert job.failure == "stale_source"
        assert job.result_json is None


@pytest.mark.parametrize("stage", ["claim", "finalize"])
async def test_actual_worker_rechecks_original_live_operator_grant_at_both_boundaries(
    ai_engine: AsyncEngine,
    triage_queue: SqlAiQueue,
    stage: str,
) -> None:
    api = await prepared(ai_engine)
    submitted = await api.enqueue()(await api.command())
    queue = triage_queue
    claimed = await queue.claim() if stage == "finalize" else None
    if stage == "finalize":
        assert claimed is not None
    await revoke_grant(api)
    if claimed is None:
        assert await queue.claim() is None
    else:
        result = await queue.complete(
            claimed, ReportTriage(Priority.HIGH, "Controlled advisory"), stopped=True
        )
        assert result.failure == Failure.ACCOUNT
    async with api.unit.sessions() as session:
        job = await session.get(AiJobRecord, submitted.observation.job_id)
        assert job is not None
        assert job.state == "failed"
        assert job.failure == "account_unavailable"
        assert job.result_json is None


async def test_success_is_advisory_only_and_later_human_review_withholds_old_priority(
    ai_engine: AsyncEngine,
    triage_queue: SqlAiQueue,
) -> None:
    api = await prepared(ai_engine)
    await api.enqueue()(await api.command())
    queue = triage_queue
    job = await queue.claim()
    assert job is not None
    terminal = await queue.complete(
        job, ReportTriage(Priority.HIGH, "Controlled private rationale"), stopped=True
    )
    assert terminal.state == JobState.SUCCEEDED
    async with api.unit.sessions() as session:
        assert tuple(await session.scalars(select(ReportReviewRevisionRecord))) == ()
    read = ReadReportTriage(api.unit, HASHER)
    current = await read(api.reports.owner.credential, api.reports.report.id)
    assert current is not None
    assert current.triage is not None
    assert current.triage.observation.priority == Priority.HIGH
    await human_review(api)
    stale = await read(api.reports.owner.credential, api.reports.report.id)
    assert stale is not None
    assert stale.triage is not None
    assert stale.triage.observation.state == JobState.SUCCEEDED
    assert stale.triage.observation.source_current is False
    assert stale.triage.observation.priority is None
    assert stale.triage.observation.rationale is None


async def test_queued_triage_cannot_execute_after_retained_google_lineage_is_banned(
    ai_engine: AsyncEngine,
    triage_queue: SqlAiQueue,
) -> None:
    api = await prepared(ai_engine)
    submitted = await api.enqueue()(await api.command())
    historical = await fresh_account(ai_engine)
    async with api.unit.sessions.begin() as session:
        subject = (
            await session.scalars(
                select(ExternalIdentityRecord.subject).where(
                    ExternalIdentityRecord.account_id == api.reports.owner.id,
                    ExternalIdentityRecord.retired_at.is_(None),
                )
            )
        ).one()
        at = (
            await session.execute(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        ).scalar_one()
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == historical)
            .values(deleted_at=at, banned_at=at)
        )
        retained = google_claim(historical, subject, at)
        retained.retired_at = at
        session.add(retained)
    executor = ControlledReportExecutor()
    assert not await ExecuteNextJob(triage_queue, executor)()
    assert executor.calls == 0
    async with api.unit.sessions() as session:
        account = await session.get(AccountRecord, api.reports.owner.id)
        assert account is not None
        assert account.banned_at is None
        assert account.deleted_at is None
        job = await session.get(AiJobRecord, submitted.observation.job_id)
        assert job is not None
        assert job.state == "failed"
        assert job.failure == "account_unavailable"
        assert job.result_json is None
