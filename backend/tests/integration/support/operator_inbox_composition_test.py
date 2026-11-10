"""Actual root/lifespan and head-migrated support sources; no standalone router."""

from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import ORIGIN, BrowserHarness, write_headers
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
PRIVATE_REPLY = "operator-inbox-private@example.test"
PRIVATE_TEXT = "PRIVATE_OPERATOR_INBOX_MESSAGE"


async def create_case(browser: BrowserHarness) -> UUID:
    prepared = await browser.client.post(
        "/api/v1/support-context", json={}, headers={"Origin": ORIGIN}
    )
    assert prepared.status_code == HTTPStatus.OK
    saved = await browser.client.post(
        "/api/v1/support-cases",
        json={
            "topic": "cannot_sign_in",
            "reply_address": PRIVATE_REPLY,
            "message": PRIVATE_TEXT,
            "details": "PRIVATE_OPERATOR_INBOX_DETAILS",
        },
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": prepared.json()["csrf_token"],
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert saved.status_code == HTTPStatus.CREATED
    return UUID(saved.json()["case_id"])


async def test_root_inbox_finds_anonymous_case_without_private_projection_and_commits_real_audit(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    case_id = await create_case(browser)
    ordinary = await actor(identity_engine, verified=False)
    browser.client.cookies.set(SESSION_COOKIE, ordinary.credential.value)
    denied = await browser.client.get("/api/v1/operator/cases")
    assert denied.status_code == HTTPStatus.FORBIDDEN
    owner = await operator(identity_engine)
    browser.client.cookies.set(SESSION_COOKIE, owner.credential.value)
    found = await browser.client.get(
        "/api/v1/operator/cases",
        params={"case_id": str(case_id), "anonymous": "true", "status": "received"},
    )
    assert found.status_code == HTTPStatus.OK
    assert found.headers["cache-control"] == "no-store"
    assert found.json()["status_semantics"] == "current_at_each_request"
    assert found.json()["next_cursor"] is None
    assert len(found.json()["cases"]) == 1
    row = found.json()["cases"][0]
    assert row["case_id"] == str(case_id)
    assert row["actor_id"] is None
    assert set(row) == {
        "case_id",
        "actor_id",
        "topic",
        "received_at",
        "status",
        "version",
        "changed_at",
    }
    empty = await browser.client.get("/api/v1/operator/cases", params={"case_id": str(uuid4())})
    assert empty.status_code == HTTPStatus.OK
    assert empty.json()["cases"] == []
    async with async_sessionmaker(identity_engine)() as session:
        audits = (
            await session.scalars(
                select(OperatorAuditRecord).where(
                    OperatorAuditRecord.action == "search_support_cases"
                )
            )
        ).all()
        assert {source.http_request_id for source in audits} == {
            UUID(found.headers["x-request-id"]),
            UUID(empty.headers["x-request-id"]),
        }
        for audit in audits:
            assert audit.operator_id == owner.id
            assert audit.outcome == "search"
            assert audit.requested_id is None
            assert audit.query_fingerprint is not None
            canonical = (
                await session.scalars(
                    select(ProductEventRecord).where(
                        ProductEventRecord.operator_audit_id == audit.id
                    )
                )
            ).one()
            assert canonical.operator_action == "search_support_cases"
    assert PRIVATE_REPLY not in found.text
    assert PRIVATE_TEXT not in found.text
    assert PRIVATE_REPLY not in caplog.text
    assert PRIVATE_TEXT not in caplog.text


async def test_root_history_exposes_original_status_grant_sources_and_audits_missing_case(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    case_id = await create_case(browser)
    owner = await operator(identity_engine)
    browser.client.cookies.set(SESSION_COOKIE, owner.credential.value)
    for status, version in (("in_review", 1), ("resolved", 2)):
        changed = await browser.client.put(
            f"/api/v1/operator/cases/{case_id}/status",
            json={"status": status, "expected_version": version},
            headers=await write_headers(browser.client),
        )
        assert changed.status_code == HTTPStatus.OK
    history = await browser.client.get(f"/api/v1/operator/cases/{case_id}/history")
    assert history.status_code == HTTPStatus.OK
    result = history.json()
    assert result["case_id"] == str(case_id)
    assert result["anchor_version"] == len(result["revisions"])
    assert result["next_cursor"] is None
    assert [row["status"] for row in result["revisions"]] == ["resolved", "in_review", "received"]
    assert [row["version"] for row in result["revisions"]] == [3, 2, 1]
    for row in result["revisions"][:-1]:
        assert row["changed_by_id"] == str(owner.id)
        assert row["operator_access_version"] == 1
    assert result["revisions"][-1]["changed_by_id"] is None
    assert result["revisions"][-1]["operator_access_version"] is None
    missing = await browser.client.get(f"/api/v1/operator/cases/{uuid4()}/history")
    assert missing.status_code == HTTPStatus.NOT_FOUND
    async with async_sessionmaker(identity_engine)() as session:
        audits = (
            await session.scalars(
                select(OperatorAuditRecord).where(
                    OperatorAuditRecord.http_request_id.in_(
                        (
                            UUID(history.headers["x-request-id"]),
                            UUID(missing.headers["x-request-id"]),
                        )
                    )
                )
            )
        ).all()
        assert {source.outcome for source in audits} == {"read", "not_found"}
        assert all(source.action == "read_support_case" for source in audits)
    assert PRIVATE_REPLY not in history.text
    assert PRIVATE_TEXT not in history.text
