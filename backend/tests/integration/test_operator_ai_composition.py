from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness
from tests.integration.operator.test_ai_jobs import INTENT_KEY, prepared
from tests.unit.operator.ai_store import RAW_INPUT, RAW_RESULT

pytestmark = pytest.mark.integration
EXPECTED_AI_INSPECTIONS = 3


async def test_root_operator_reads_retained_ai_without_executor_or_source_authority(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    jobs = await prepared(identity_engine)
    async with jobs.uow.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == jobs.target.id)
            .values(deleted_at=func.clock_timestamp())
        )
    caplog.set_level("INFO", logger="studymate.http")
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, jobs.owner.credential.value)
    root = f"/api/v1/operator/accounts/{jobs.target.id}/ai-jobs"
    listing = await browser.client.get(root)
    assert listing.status_code == HTTPStatus.OK
    assert [row["id"] for row in listing.json()["jobs"]] == [str(jobs.job_id)]
    assert RAW_INPUT not in listing.text
    detail = await browser.client.get(f"{root}/{jobs.job_id}")
    assert detail.status_code == HTTPStatus.OK
    assert detail.json()["input_json_raw"] == RAW_INPUT
    assert detail.json()["result_json_raw"] == RAW_RESULT
    assert detail.json()["representation"] == "raw_stored_text_not_current_task_schema"
    assert detail.headers["cache-control"] == "no-store"
    assert detail.headers["x-request-id"]
    assert str(jobs.token) not in detail.text
    assert INTENT_KEY not in detail.text
    missing = await browser.client.get(f"{root}/{uuid4()}")
    assert missing.status_code == HTTPStatus.NOT_FOUND
    async with jobs.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == EXPECTED_AI_INSPECTIONS
        assert all(audit.action == "read_account" for audit in audits)
        assert all(audit.requested_id == jobs.target.id for audit in audits)
        assert all(audit.result_ids == [jobs.target.id] for audit in audits)
        events = tuple(await session.scalars(select(ProductEventRecord)))
        assert {event.operator_audit_id for event in events} == {audit.id for audit in audits}
    assert RAW_INPUT not in caplog.text
    assert RAW_RESULT not in caplog.text
    assert str(jobs.token) not in caplog.text
