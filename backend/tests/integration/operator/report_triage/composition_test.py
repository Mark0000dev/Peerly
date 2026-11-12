"""Actual root, isolated admission pool, durable queue and controlled typed executor."""

from dataclasses import dataclass
from http import HTTPStatus

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.application.ai.worker import ExecuteNextJob
from studymate.domain.ai.tasks import AiResult, AiTask, Priority, ReportTriage, TriageReport
from studymate.infrastructure.ai.models import AiJobRecord
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.lifecycle.models import LifecycleRevisionRecord
from studymate.infrastructure.operator.photo_review_models import OperatorPhotoReviewRecord
from studymate.infrastructure.operator.report_triage_models import (
    ReportTriageEvidenceRecord,
    ReportTriageSubmissionRecord,
)
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.report_moderation.models import ReportReviewRevisionRecord
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.identity import IdentityResponse
from studymate.presentation.operator.report_triage_models import ReportTriageResponse
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.operator.report_triage.fixture import TriageCase, prepared

pytestmark = pytest.mark.integration
ADMISSION_POOL_SIZE = 2
RATIONALE = "Controlled advisory; a human decides any action."


@dataclass(slots=True)
class ControlledReportExecutor:
    calls: int = 0

    async def execute(self, task: AiTask, budget_seconds: float) -> AiResult:
        assert isinstance(task, TriageReport)
        assert task.evidence
        assert budget_seconds > 0
        self.calls += 1
        return ReportTriage(Priority.HIGH, RATIONALE)


async def assert_actual_pool_isolation(browser: BrowserHarness, api: TriageCase, path: str) -> None:
    http = browser.client
    pool = browser.ai_engine.pool
    assert isinstance(pool, AsyncAdaptedQueuePool)
    assert pool.size() == ADMISSION_POOL_SIZE
    # Occupy the actual dedicated pool. Internal AI cannot borrow the core pool,
    # and ordinary manual inspection must remain available without an AI slot.
    async with browser.ai_engine.connect(), browser.ai_engine.connect():
        unavailable = await http.get(path + "/triage-source")
        assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert unavailable.headers["Retry-After"] == "1"
        assert "job_id" not in unavailable.json()
        assert (await http.get(path)).status_code == HTTPStatus.OK
        assert (await http.get("/api/v1/me")).status_code == HTTPStatus.OK
    assert pool.checkedout() == 0
    async with api.unit.sessions() as session:
        assert tuple(await session.scalars(select(AiJobRecord))) == ()
        assert tuple(await session.scalars(select(ReportTriageEvidenceRecord))) == ()
        assert tuple(await session.scalars(select(ReportTriageSubmissionRecord))) == ()


def assert_actual_pool_released(browser: BrowserHarness) -> None:
    pool = browser.ai_engine.pool
    assert isinstance(pool, AsyncAdaptedQueuePool)
    assert pool.checkedout() == 0


async def assert_actual_canonical_and_no_moderation(
    browser: BrowserHarness, api: TriageCase, payload: object
) -> None:
    http = browser.client
    queued = ReportTriageResponse.model_validate(payload)
    event = await http.get(f"/api/v1/operator/events/{queued.event_id}")
    assert event.status_code == HTTPStatus.OK
    assert event.json()["kind"] == "triage.submitted"
    assert event.json()["subject_account_id"] == str(api.reports.owner.id)
    assert event.json()["origin"]["http_request_id"] == str(queued.http_request_id)
    assert any(
        source["kind"] == "report_triage_submission"
        and source["id"] == str(queued.job_id)
        and source["owner_id"] == str(queued.operator_id)
        for source in event.json()["sources"]
    )
    assert RATIONALE not in event.text
    async with api.unit.sessions() as session:
        assert len(tuple(await session.scalars(select(AiJobRecord)))) == 1
        assert len(tuple(await session.scalars(select(ReportTriageEvidenceRecord)))) == 1
        assert len(tuple(await session.scalars(select(ReportTriageSubmissionRecord)))) == 1
        assert tuple(await session.scalars(select(ReportReviewRevisionRecord))) == ()
        assert tuple(await session.scalars(select(OperatorPhotoReviewRecord))) == ()
        assert tuple(await session.scalars(select(LifecycleRevisionRecord))) == ()
        assert (
            tuple(
                await session.scalars(
                    select(AccountRecord).where(
                        AccountRecord.banned_at.is_not(None) | AccountRecord.deleted_at.is_not(None)
                    )
                )
            )
            == ()
        )


async def test_actual_root_internal_triage_queue_result_and_canonical_drilldown(
    browser: BrowserHarness,
    ai_engine: AsyncEngine,
    triage_queue: SqlAiQueue,
) -> None:
    api = await prepared(ai_engine)
    http = browser.client
    http.cookies.clear()
    http.cookies.set(SESSION_COOKIE, api.reports.owner.credential.value)
    identity_response = await http.get("/api/v1/me")
    assert identity_response.status_code == HTTPStatus.OK
    identity = IdentityResponse.model_validate(identity_response.json())
    assert identity.account_id == api.reports.owner.id
    assert identity.membership_status == "unverified"
    path = f"/api/v1/operator/reports/{api.reports.report.id}"

    empty = await http.get(path + "/triage")
    assert empty.status_code == HTTPStatus.OK
    assert empty.json()["triage"] is None
    await assert_actual_pool_isolation(browser, api, path)

    source = await http.get(path + "/triage-source")
    assert source.status_code == HTTPStatus.OK
    assert source.json()["available"] is True
    assert source.json()["source_token"]
    assert source.headers["Cache-Control"] == "no-store"
    headers = await write_headers(http)
    body = {"source_token": source.json()["source_token"]}
    submitted = await http.post(path + "/triage", json=body, headers=headers)
    assert submitted.status_code == HTTPStatus.OK
    queued = submitted.json()
    assert queued["state"] == "queued"
    assert queued["priority"] is None
    assert queued["rationale"] is None
    assert queued["operator_id"] == str(api.reports.owner.id)
    assert queued["http_request_id"] == submitted.headers["X-Request-ID"]
    assert (await http.post(path + "/triage", json=body, headers=headers)).json() == queued
    pending = await http.get(path + "/triage")
    assert pending.status_code == HTTPStatus.OK
    assert pending.json()["triage"] == queued

    # Internal operator permission never opens ordinary verified-student AI.
    student = await http.post(
        "/api/v1/ai/jobs",
        json={
            "kind": "clarify_goal",
            "source": {"kind": "resource", "id": str(api.reports.report.id), "version": 1},
            "text": "Explicit ordinary student goal",
        },
        headers=await write_headers(http),
    )
    assert student.status_code == HTTPStatus.FORBIDDEN
    executor = ControlledReportExecutor()
    assert await ExecuteNextJob(triage_queue, executor)()
    assert executor.calls == 1
    completed = await http.get(path + "/triage")
    assert completed.status_code == HTTPStatus.OK
    actual = completed.json()["triage"]
    assert actual["job_id"] == queued["job_id"]
    assert actual["state"] == "succeeded"
    assert actual["source_current"] is True
    assert actual["priority"] == "high"
    assert actual["rationale"] == RATIONALE
    assert actual["event_id"] == queued["event_id"]
    assert completed.headers["Referrer-Policy"] == "no-referrer"
    assert_actual_pool_released(browser)

    await assert_actual_canonical_and_no_moderation(browser, api, queued)
