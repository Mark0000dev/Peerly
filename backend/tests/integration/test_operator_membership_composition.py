"""Actual root factory, browser guards, manual provenance and no registration side effects."""

from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.infrastructure.operator.membership_verification_models import (
    OperatorMembershipVerificationRecord,
)
from studymate.infrastructure.persistence.email_models import EmailChallengeRecord
from studymate.infrastructure.persistence.identity_models import InstitutionalBindingRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.operator.membership_verification_test import prepared

pytestmark = pytest.mark.integration


async def test_root_manual_verification_real_source_idempotency_and_correlated_event(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    case = await prepared(identity_engine)
    browser.client.cookies.set(SESSION_COOKIE, case.operator.credential.value)
    root = f"/api/v1/operator/accounts/{case.target.id}"
    context = await browser.client.get(root + "/membership-verification")
    assert context.status_code == HTTPStatus.OK
    assert context.headers["cache-control"] == "no-store"
    headers = await write_headers(browser.client)
    action_id = uuid4()
    headers["X-Action-ID"] = str(action_id)
    body = {
        "expected_google_identity_id": str(case.command.expected_google_identity_id),
        "expected_challenge_id": str(case.command.expected_challenge_id),
        "expected_email": case.command.expected_email.value,
    }
    result = await browser.client.post(
        root + "/membership-verifications", json=body, headers=headers
    )
    assert result.status_code == HTTPStatus.OK
    assert result.headers["cache-control"] == "no-store"
    replay = await browser.client.post(
        root + "/membership-verifications", json=body, headers=headers
    )
    assert replay.json() == result.json()
    async with case.sessions() as session:
        proof = (await session.scalars(select(OperatorMembershipVerificationRecord))).one()
        binding = await session.get(InstitutionalBindingRecord, case.target.id)
        event = await session.get(ProductEventRecord, proof.event_id)
        challenge = await session.get(EmailChallengeRecord, proof.challenge_id)
        assert binding is not None
        assert event is not None
        assert challenge is not None
        assert event.occurred_at == binding.verified_at
        assert event.action_id == action_id
        assert event.occurrence_key.startswith("smv1:")
        assert challenge.consumed_at is None
    browser.client.cookies.set(SESSION_COOKIE, case.target.credential.value)
    onboarding = await browser.client.get("/api/v1/me/onboarding")
    assert onboarding.status_code == HTTPStatus.OK
    assert onboarding.json()["registered"] is False
    assert onboarding.json()["setup_complete"] is False


async def test_root_manual_endpoint_does_not_bypass_csrf_or_json_budget(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    case = await prepared(identity_engine)
    browser.client.cookies.set(SESSION_COOKIE, case.operator.credential.value)
    path = f"/api/v1/operator/accounts/{case.target.id}/membership-verifications"
    oversized = await browser.client.post(
        path,
        content=b"x" * 8193,
        headers={
            "Content-Type": "application/json",
        },
    )
    assert oversized.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    denied = await browser.client.post(
        path,
        json={
            "expected_google_identity_id": str(case.command.expected_google_identity_id),
            "expected_challenge_id": str(case.command.expected_challenge_id),
            "expected_email": case.command.expected_email.value,
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert denied.status_code == HTTPStatus.FORBIDDEN
    async with case.sessions() as session:
        assert await session.get(InstitutionalBindingRecord, case.target.id) is None
