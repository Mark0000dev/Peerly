from dataclasses import dataclass
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.operator.models import (
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.support.models import SupportCaseRecord, SupportRevisionRecord
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.timeline_models import OperatorAuditDetailResponse
from studymate.presentation.support.router import SUPPORT_COOKIE
from tests.integration.http_identity import ORIGIN, BrowserHarness, write_headers
from tests.integration.operator.test_reads import operator

pytestmark = pytest.mark.integration
PRIVATE_NOTES_SENTINEL = "Cannot sign in"


async def test_public_support_needs_exact_origin_csrf_and_proof_then_recovers_without_login(
    browser: BrowserHarness,
) -> None:
    path = "/api/v1/support-cases"
    context = "/api/v1/support-context"
    assert (await browser.client.post(context, json={})).status_code == HTTPStatus.FORBIDDEN
    prepared = await browser.client.post(context, json={}, headers={"Origin": ORIGIN})
    assert prepared.status_code == HTTPStatus.OK
    assert prepared.headers["cache-control"] == "no-store"
    assert "HttpOnly" in prepared.headers["set-cookie"]
    headers = {
        "Origin": ORIGIN,
        "X-CSRF-Token": prepared.json()["csrf_token"],
        "Idempotency-Key": "support_001",
    }
    body = {
        "topic": "deleted_account",
        "reply_address": "private@example.test",
        "message": "Private cannot sign in",
    }
    denied = await browser.client.post(
        path, json=body, headers={"Origin": ORIGIN, "Idempotency-Key": "support_001"}
    )
    assert denied.status_code == HTTPStatus.FORBIDDEN
    saved = await browser.client.post(path, json=body, headers=headers)
    assert saved.status_code == HTTPStatus.CREATED
    assert "private" not in saved.text.lower()
    case_id = saved.json()["case_id"]
    assert (await browser.client.post(path, json=body, headers=headers)).json() == saved.json()
    assert (await browser.client.get(f"{path}/{case_id}")).json() == saved.json()
    browser.client.cookies.clear()
    assert (await browser.client.get(f"{path}/{case_id}")).status_code == HTTPStatus.NOT_FOUND
    await browser.client.post(context, json={}, headers={"Origin": ORIGIN})
    assert (await browser.client.get(path)).json() == {"cases": []}
    assert (await browser.client.get(f"{path}/{case_id}")).status_code == HTTPStatus.NOT_FOUND


async def test_operator_status_is_real_audited_revision_and_public_replay_stays_received(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    prepared = await browser.client.post(
        "/api/v1/support-context", json={}, headers={"Origin": ORIGIN}
    )
    headers = {
        "Origin": ORIGIN,
        "X-CSRF-Token": prepared.json()["csrf_token"],
        "Idempotency-Key": "support_001",
    }
    body = {
        "topic": "cannot_sign_in",
        "reply_address": "private@example.test",
        "message": "Cannot sign in",
    }
    saved = await browser.client.post("/api/v1/support-cases", json=body, headers=headers)
    assert saved.status_code == HTTPStatus.CREATED
    case_id = UUID(saved.json()["case_id"])
    path = f"/api/v1/operator/cases/{case_id}"
    owner = await operator(identity_engine)
    browser.client.cookies.set(SESSION_COOKIE, owner.credential.value)
    detail = await browser.client.get(path)
    assert detail.status_code == HTTPStatus.OK
    assert detail.json()["message"] == body["message"]
    status_headers = await write_headers(browser.client)
    update = {"status": "in_review", "expected_version": 1}
    changed = await browser.client.put(f"{path}/status", json=update, headers=status_headers)
    assert changed.status_code == HTTPStatus.OK
    assert changed.json()["status"] == "in_review"
    assert (
        await browser.client.put(f"{path}/status", json=update, headers=status_headers)
    ).json() == changed.json()
    assert (await browser.client.get(f"/api/v1/support-cases/{case_id}")).json() == changed.json()
    assert (
        await browser.client.post("/api/v1/support-cases", json=body, headers=headers)
    ).json() == saved.json()
    missing = await browser.client.get(f"/api/v1/operator/cases/{uuid4()}")
    assert missing.status_code == HTTPStatus.NOT_FOUND
    async with async_sessionmaker(identity_engine)() as session:
        case = await session.get(SupportCaseRecord, case_id)
        assert case is not None
        assert case.actor_id is None
        assert case.http_request_id == UUID(saved.headers["x-request-id"])
        revision = await session.get(SupportRevisionRecord, (case_id, changed.json()["version"]))
        assert revision is not None
        assert revision.changed_by_id == owner.id
        assert revision.operator_access_version == 1
        assert (
            await session.scalars(
                select(OperatorAuditRecord).where(
                    OperatorAuditRecord.resource_kind == "support_case"
                )
            )
        ).all()
        events = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.support_case_id == case_id)
            )
        ).all()
        assert len(events) == 1
        event = events[0]
        assert event.kind == "support.status_changed"
        assert event.account_id == owner.id
        assert event.support_case_version == revision.version
        assert event.request_id == UUID(changed.headers["x-request-id"])
        audits = (
            await session.scalars(
                select(OperatorAuditRecord).where(
                    OperatorAuditRecord.resource_kind == "support_case"
                )
            )
        ).all()
        assert {audit.outcome for audit in audits} == {"read", "not_found"}
        for audit in audits:
            canonical = (
                await session.scalars(
                    select(ProductEventRecord).where(
                        ProductEventRecord.operator_audit_id == audit.id
                    )
                )
            ).one()
            assert canonical.account_id == owner.id
            assert canonical.operator_action == "read_support_case"
            assert PRIVATE_NOTES_SENTINEL not in repr(canonical.__dict__)
    await assert_original_support_audit(
        browser,
        identity_engine,
        SupportAuditExpectation(
            case_id, owner.id, UUID(detail.headers["x-request-id"]), body["reply_address"]
        ),
    )
    browser.client.cookies.delete(SUPPORT_COOKIE)


@dataclass(frozen=True, slots=True)
class SupportAuditExpectation:
    case_id: UUID
    operator_id: UUID
    request_id: UUID
    reply_address: str


async def assert_original_support_audit(
    browser: BrowserHarness, engine: AsyncEngine, expected: SupportAuditExpectation
) -> None:
    async with async_sessionmaker(engine)() as session:
        original = (
            await session.scalars(
                select(OperatorAuditRecord).where(
                    OperatorAuditRecord.http_request_id == expected.request_id,
                    OperatorAuditRecord.action == "read_support_case",
                )
            )
        ).one()
        original_id = original.id
        grant = await session.get(
            OperatorAccessRevisionRecord,
            (original.operator_id, original.operator_access_version),
        )
        assert grant is not None
        grant_version, grant_changed_at = grant.version, grant.changed_at
    inspected = await browser.client.get(f"/api/v1/operator/audits/{original_id}")
    assert inspected.status_code == HTTPStatus.OK
    assert inspected.headers["cache-control"] == "no-store"
    actual = OperatorAuditDetailResponse.model_validate(inspected.json())
    assert actual.id == original_id
    assert actual.operator_id == expected.operator_id
    assert actual.operator_access_version == grant_version
    assert actual.operator_access_changed_at == grant_changed_at
    assert actual.action == "read_support_case"
    assert actual.outcome == "read"
    assert actual.requested_kind == "support_case"
    assert actual.requested_id == expected.case_id
    assert tuple((ref.kind, ref.id) for ref in actual.results) == (
        ("support_case", expected.case_id),
    )
    assert actual.origin.http_request_id == expected.request_id
    assert not actual.query_fingerprinted
    for private_field in (
        "reply_address",
        "message",
        "details",
        "proof_digest",
        "query_fingerprint",
    ):
        assert private_field not in inspected.json()
    assert expected.reply_address not in inspected.text
    assert PRIVATE_NOTES_SENTINEL not in inspected.text
