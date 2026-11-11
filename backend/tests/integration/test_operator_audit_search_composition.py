"""Actual root list filters the original journal and audits the search itself."""

from http import HTTPStatus

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness
from tests.integration.migrations import run_revision_step
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor
from tests.integration.test_operator_event_schema import seeded_audit

pytestmark = pytest.mark.integration


async def test_root_audit_search_preserves_original_grant_and_retains_current_search(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    seed = await seeded_audit(identity_engine)
    student = await actor(identity_engine)
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, student.credential.value)
    denied = await browser.client.get("/api/v1/operator/audits")
    assert denied.status_code == HTTPStatus.FORBIDDEN
    owner = await operator(identity_engine)
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owner.credential.value)
    response = await browser.client.get(
        "/api/v1/operator/audits",
        params={
            "operator_id": str(seed.access.account_id),
            "action": "search_accounts",
        },
    )
    assert response.status_code == HTTPStatus.OK
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert [row["id"] for row in body["audits"]] == [str(seed.id)]
    assert body["audits"][0]["operator_id"] == str(seed.access.account_id)
    assert body["audits"][0]["operator_access_version"] == seed.access.version
    assert "query_fingerprint" not in body["audits"][0]
    async with async_sessionmaker(identity_engine)() as session:
        searches = tuple(
            await session.scalars(
                select(OperatorAuditRecord).where(OperatorAuditRecord.action == "search_audits")
            )
        )
    assert len(searches) == 1
    assert searches[0].operator_id == owner.id
    assert searches[0].result_ids == [seed.id]
    async with identity_engine.begin() as connection:
        with pytest.raises(RuntimeError, match="retained operator-audit search facts"):
            await connection.run_sync(run_revision_step, "0057_operator_audit_search", "downgrade")
