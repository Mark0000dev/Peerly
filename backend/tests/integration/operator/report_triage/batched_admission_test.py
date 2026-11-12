import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.ai.policy import AdmissionPolicy
from studymate.application.ai.ports import AiQuotaError, AiUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.operator.report_triage import EnqueueReportTriage
from studymate.domain.ai.jobs import Versions
from studymate.domain.ai.tasks import Priority, ReportTriage
from studymate.domain.operator.report_triage import ReportTriageSubmission
from studymate.infrastructure.ai.models import (
    AiBudgetRecord,
    AiIntentRecord,
    AiJobRecord,
    AiSlotRecord,
)
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.ai.runtime.health import REPORT_GUARD_VERSION, SqlRuntimeHealth
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
    record_report_triage_submission,
)
from tests.integration.operator.report_triage.fixture import CODEC, prepared
from tests.integration.operator.report_triage.worker_test import human_review
from tests.integration.requests.fixture import FINGERPRINTER, HASHER

pytestmark = pytest.mark.integration
EXPECTED_INTENTS = 2


async def test_matching_input_new_key_preserves_original_proof_budget_and_source(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    command = await api.command()
    first = await api.enqueue()(command)
    second = await api.enqueue()(replace(command, intent_key=IntentKey(str(uuid4()))))
    assert first == second
    async with api.unit.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AiJobRecord)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(AiIntentRecord))
            == EXPECTED_INTENTS
        )
        assert (
            await session.scalar(select(func.count()).select_from(ReportTriageEvidenceRecord)) == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(ReportTriageSubmissionRecord))
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "triage.submitted")
            )
            == 1
        )
        budget = await session.get(AiBudgetRecord, api.reports.owner.id)
        assert budget is not None
        assert budget.tokens == api.unit.policy.bucket_capacity - 1


async def cancel_canonical(session: AsyncSession, source: ReportTriageSubmission) -> None:
    await record_report_triage_submission(session, source)
    raise asyncio.CancelledError


async def test_cancellation_after_actual_atomic_write_rolls_back_every_source(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    command = await api.command()
    unit = SqlOperatorReportTriageUnitOfWork(
        api.unit.sessions, record_operator_audit, cancel_canonical
    )
    with pytest.raises(asyncio.CancelledError):
        await EnqueueReportTriage(unit, HASHER, FINGERPRINTER, CODEC)(command)
    async with unit.sessions() as session:
        for model in (
            AiJobRecord,
            AiIntentRecord,
            AiBudgetRecord,
            ReportTriageEvidenceRecord,
            ReportTriageSubmissionRecord,
        ):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "triage.submitted")
            )
            == 0
        )


@pytest.mark.parametrize(
    ("tokens", "elapsed", "allowed"),
    [(0.0, 0, False), (0.0, 61, True), (1.0, 0, True), (0.0, -60, False)],
)
async def test_actual_bucket_refill_and_outstanding_guards_are_not_skipped(
    ai_engine: AsyncEngine, tokens: float, elapsed: int, allowed: bool
) -> None:
    api = await prepared(ai_engine)
    command = await api.command()
    async with api.unit.sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        session.add(
            AiBudgetRecord(
                actor_id=api.reports.owner.id,
                tokens=tokens,
                refilled_at=at - timedelta(seconds=elapsed),
                last_served=0,
            )
        )
    if allowed:
        await api.enqueue()(command)
    else:
        with pytest.raises(AiQuotaError):
            await api.enqueue()(command)
    async with api.unit.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AiJobRecord)) == int(allowed)


async def test_expired_queue_transition_retains_terminal_event_before_new_admission(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    limited = replace(api.unit, policy=AdmissionPolicy(queue_limit=1, internal_reserve=0))
    enqueue = EnqueueReportTriage(limited, HASHER, FINGERPRINTER, CODEC)
    first = await enqueue(await api.command())
    await human_review(api)
    async with limited.sessions.begin() as session:
        await session.execute(
            update(AiJobRecord)
            .where(AiJobRecord.id == first.observation.job_id)
            .values(deadline=AiJobRecord.created_at + timedelta(microseconds=1))
        )
    second = await enqueue(await api.command("after-expired-queue"))
    async with limited.sessions() as session:
        old = await session.get(AiJobRecord, first.observation.job_id)
        current = await session.get(AiJobRecord, second.observation.job_id)
        assert old is not None
        assert old.state == "expired"
        assert current is not None
        assert current.state == "queued"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(
                    ProductEventRecord.ai_job_id == old.id,
                    ProductEventRecord.kind == "ai_job.completed",
                    ProductEventRecord.ai_state == "expired",
                )
            )
            == 1
        )


@pytest.mark.parametrize("condition", ["missing", "stale", "paused", "circuit"])
async def test_canonical_runtime_failures_do_not_create_fake_pending_state(
    identity_engine: AsyncEngine, condition: str
) -> None:
    ai_engine = identity_engine
    api = await prepared(ai_engine)
    command = await api.command()
    health = SqlRuntimeHealth(
        api.unit.sessions,
        uuid4(),
        Versions("controlled-negative"),
        report_guard_version=REPORT_GUARD_VERSION,
    )
    if condition != "missing":
        await health.register()
        await health.heartbeat(ready=True)
    try:
        async with api.unit.sessions.begin() as session:
            at = await session.scalar(select(func.clock_timestamp()))
            assert isinstance(at, datetime)
            if condition == "missing":
                await session.execute(delete(AiSlotRecord))
            elif condition == "stale":
                await session.execute(
                    update(AiSlotRecord).values(
                        runtime_started_at=at - timedelta(minutes=2),
                        runtime_heartbeat_at=at - timedelta(minutes=1),
                        runtime_valid_until=at - timedelta(minutes=1) + timedelta(seconds=15),
                    )
                )
            elif condition == "paused":
                await session.execute(
                    update(AiSlotRecord).values(paused_until=at + timedelta(minutes=1))
                )
            else:
                await session.execute(update(AiSlotRecord).values(circuit="auth_unavailable"))
        with pytest.raises(AiUnavailableError):
            await api.enqueue()(command)
        async with api.unit.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(AiJobRecord)) == 0
            assert (
                await session.scalar(select(func.count()).select_from(ReportTriageEvidenceRecord))
                == 0
            )
    finally:
        if condition != "missing":
            await health.revoke(clean=True)


async def test_real_actor_outstanding_limit_preserves_first_job_and_budget(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    limited = replace(api.unit, policy=AdmissionPolicy(student_outstanding=1))
    enqueue = EnqueueReportTriage(limited, HASHER, FINGERPRINTER, CODEC)
    first = await enqueue(await api.command())
    await human_review(api)
    with pytest.raises(AiQuotaError):
        await enqueue(await api.command("next-outstanding-proof"))
    async with limited.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AiJobRecord)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ReportTriageEvidenceRecord)) == 1
        )
        job = await session.get(AiJobRecord, first.observation.job_id)
        assert job is not None
        assert job.state == "queued"


async def test_new_intent_after_terminal_job_reuses_retained_snapshot_without_new_source(
    ai_engine: AsyncEngine,
    triage_queue: SqlAiQueue,
) -> None:
    api = await prepared(ai_engine)
    first = await api.enqueue()(await api.command())
    claimed = await triage_queue.claim()
    assert claimed is not None
    await triage_queue.complete(
        claimed, ReportTriage(Priority.LOW, "Controlled retained advice"), stopped=True
    )
    second = await api.enqueue()(await api.command("same-source-after-terminal"))
    assert second.observation.job_id != first.observation.job_id
    assert second.submission.source_version == first.submission.source_version
    async with api.unit.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ReportTriageEvidenceRecord)) == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(AiJobRecord)) == EXPECTED_INTENTS
        )
        assert (
            await session.scalar(select(func.count()).select_from(ReportTriageSubmissionRecord))
            == EXPECTED_INTENTS
        )
