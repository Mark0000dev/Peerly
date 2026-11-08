from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.goal_models import GoalRevisionRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.profile_models import ProfileRevisionRecord
from studymate.infrastructure.persistence.report_models import ProfileReportRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness
from tests.integration.operator.test_goals import RAW_CONTEXT
from tests.integration.operator.test_goals import prepared as goal_fixture
from tests.integration.operator.test_help_history import prepared as help_fixture
from tests.integration.operator.test_profile_history import RAW_ABOUT
from tests.integration.operator.test_profile_history import prepared as history_fixture
from tests.integration.operator.test_reads import operator
from tests.integration.operator.test_reports import RAW_COMMENT
from tests.integration.operator.test_reports import reports as report_fixture
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
ROOT = "/api/v1/operator"
EXPECTED_READS = 12
EXPECTED_STUDY_READS = 3


async def test_root_operator_requires_explicit_grant_and_audits_all_read_routes(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    student = await actor(identity_engine)
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, student.credential.value)
    for path in (
        "/accounts",
        "/reports",
        f"/reports/{uuid4()}",
        f"/accounts/{student.id}/profile-history",
        f"/accounts/{student.id}/ai-jobs",
        f"/accounts/{student.id}/ai-jobs/{uuid4()}",
        f"/accounts/{student.id}/photo-uploads",
        f"/accounts/{student.id}/photo-uploads/{uuid4()}/history",
        f"/accounts/{student.id}/photo-uploads/{uuid4()}/attempts/{uuid4()}/original",
        f"/accounts/{student.id}/help-history",
        f"/accounts/{student.id}/goals",
        f"/accounts/{student.id}/goals/{uuid4()}/history",
    ):
        denied = await browser.client.get(f"{ROOT}{path}")
        assert denied.status_code == HTTPStatus.FORBIDDEN
        assert denied.json()["code"] == "operator_access_denied"
    owner = await operator(identity_engine)
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owner.credential.value)
    listing = await browser.client.get(f"{ROOT}/accounts")
    detail = await browser.client.get(f"{ROOT}/accounts/{student.id}")
    missing = await browser.client.get(f"{ROOT}/conversations/{uuid4()}/messages")
    assert missing.status_code == HTTPStatus.NOT_FOUND
    reports = await browser.client.get(f"{ROOT}/reports")
    report = await browser.client.get(f"{ROOT}/reports/{uuid4()}")
    assert report.status_code == HTTPStatus.NOT_FOUND
    history = await browser.client.get(f"{ROOT}/accounts/{student.id}/profile-history")
    assert history.json()["account_id"] == str(student.id)
    help_history = await browser.client.get(f"{ROOT}/accounts/{student.id}/help-history")
    assert help_history.json()["revisions"] == []
    goals = await browser.client.get(f"{ROOT}/accounts/{student.id}/goals")
    assert goals.json()["goals"] == []
    missing_goal = await browser.client.get(f"{ROOT}/accounts/{student.id}/goals/{uuid4()}/history")
    assert missing_goal.status_code == HTTPStatus.NOT_FOUND
    timeline = await browser.client.get(f"{ROOT}/events")
    async with async_sessionmaker(identity_engine)() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).first()
        event = (await session.scalars(select(ProductEventRecord))).first()
        assert audit is not None
        assert event is not None
        audit_id, event_id = audit.id, event.id
    event_response = await browser.client.get(f"{ROOT}/events/{event_id}")
    audit_response = await browser.client.get(f"{ROOT}/audits/{audit_id}")
    for response in (
        listing,
        detail,
        reports,
        history,
        help_history,
        goals,
        timeline,
        event_response,
        audit_response,
    ):
        assert response.status_code == HTTPStatus.OK
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-request-id"]
    async with async_sessionmaker(identity_engine)() as session:
        audits = tuple((await session.scalars(select(OperatorAuditRecord))).all())
        events = tuple((await session.scalars(select(ProductEventRecord))).all())
        assert len(audits) == EXPECTED_READS
        assert {event.operator_audit_id for event in events} == {audit.id for audit in audits}
        assert all(audit.operator_id == owner.id for audit in audits)


async def test_root_operator_retained_report_and_profile_history_are_audited_not_discovered(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    reports = await report_fixture(identity_engine)
    history = await history_fixture(identity_engine)
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(ProfileReportRecord)
            .where(ProfileReportRecord.id == reports.report.id)
            .values(comment=RAW_COMMENT)
        )
        await session.execute(
            update(ProfileRevisionRecord)
            .where(
                ProfileRevisionRecord.account_id == history.target.id,
                ProfileRevisionRecord.version == 1,
            )
            .values(about=RAW_ABOUT)
        )
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id.in_((history.target.id, reports.target.id)))
            .values(deleted_at=func.clock_timestamp(), banned_at=func.clock_timestamp())
        )
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, reports.owner.credential.value)
    listing = await browser.client.get(
        f"{ROOT}/reports", params={"target_id": str(reports.target.id)}
    )
    assert listing.status_code == HTTPStatus.OK
    assert [row["id"] for row in listing.json()["reports"]] == [str(reports.report.id)]
    assert RAW_COMMENT not in listing.text
    detail = await browser.client.get(f"{ROOT}/reports/{reports.report.id}")
    assert detail.status_code == HTTPStatus.OK
    assert detail.json()["comment"] == RAW_COMMENT
    revisions = await browser.client.get(f"{ROOT}/accounts/{history.target.id}/profile-history")
    assert revisions.status_code == HTTPStatus.OK
    assert [row["version"] for row in revisions.json()["revisions"]] == [3, 2, 1]
    assert revisions.json()["revisions"][-1]["about"] == RAW_ABOUT
    async with async_sessionmaker(identity_engine)() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert tuple(sorted(audit.action for audit in audits)) == (
            "read_account",
            "read_report",
            "search_reports",
        )
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
        assert {event.operator_audit_id for event in events} == {audit.id for audit in audits}
    assert RAW_ABOUT not in caplog.text
    assert RAW_COMMENT not in caplog.text


async def test_root_operator_help_and_all_goal_versions_survive_target_deletion(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    goals = await goal_fixture(identity_engine)
    help_history = await help_fixture(identity_engine)
    async with goals.uow.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id.in_((goals.target.id, help_history.target.id)))
            .values(deleted_at=func.clock_timestamp())
        )
        await session.execute(
            update(GoalRevisionRecord)
            .where(GoalRevisionRecord.goal_id == goals.ended_id, GoalRevisionRecord.version == 1)
            .values(context=RAW_CONTEXT)
        )
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, goals.owner.credential.value)
    roots = await browser.client.get(f"{ROOT}/accounts/{goals.target.id}/goals")
    assert roots.status_code == HTTPStatus.OK
    assert {row["id"] for row in roots.json()["goals"]} == {
        str(goals.ended_id),
        str(goals.active_id),
    }
    history = await browser.client.get(
        f"{ROOT}/accounts/{goals.target.id}/goals/{goals.ended_id}/history"
    )
    assert history.status_code == HTTPStatus.OK
    assert [row["version"] for row in history.json()["revisions"]] == [3, 2, 1]
    assert history.json()["revisions"][-1]["context"] == RAW_CONTEXT
    help_response = await browser.client.get(
        f"{ROOT}/accounts/{help_history.target.id}/help-history"
    )
    assert help_response.status_code == HTTPStatus.OK
    assert [row["version"] for row in help_response.json()["revisions"]] == [3, 2, 1]
    assert help_response.json()["revisions"][1]["selections"] == []
    assert RAW_CONTEXT not in caplog.text
    async with goals.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == EXPECTED_STUDY_READS
        assert all(audit.action == "read_account" for audit in audits)
        assert all(audit.outcome == "read" for audit in audits)
        assert {audit.requested_id for audit in audits} == {goals.target.id, help_history.target.id}
