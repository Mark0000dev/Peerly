from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.email_delivery import (
    DeliverVerificationEmail,
    DeliveryStep,
    VerificationEmail,
)
from studymate.application.identity.sessions import SessionCredential
from studymate.infrastructure.persistence.email_delivery import SqlEmailWorkerUnitOfWork
from studymate.infrastructure.persistence.registration_models import (
    PolicyDocumentRecord,
    RegistrationReceiptRecord,
)
from studymate.infrastructure.security.email_vault import AeadEmailVault
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.identity import ChallengeResponse, IdentityResponse
from studymate.presentation.registration_models import (
    PolicyStatusResponse,
    PublishedPolicyResponse,
    RegistrationContextResponse,
    RegistrationReceiptResponse,
)
from tests.integration.http_identity import BrowserHarness, login, write_headers
from tests.integration.onboarding_fixture import ready_setup

pytestmark = pytest.mark.integration


class Sender:
    def __init__(self) -> None:
        self.code: str | None = None

    async def send(self, message: VerificationEmail, _delivery_id: object) -> None:
        self.code = message.code.value


async def verify_student(browser: BrowserHarness, engine: AsyncEngine) -> None:
    client = browser.client
    await login(client)
    response = await client.post(
        "/api/v1/auth/email-challenges",
        json={"email": "tp@mail.apu.edu.my"},
        headers=await write_headers(client),
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    challenge = ChallengeResponse.model_validate(response.json())
    sender = Sender()
    worker = DeliverVerificationEmail(
        SqlEmailWorkerUnitOfWork(async_sessionmaker(engine)),
        sender,
        AeadEmailVault(bytes.fromhex("03" * 32), bytes.fromhex("01" * 32)),
    )
    assert await worker() == DeliveryStep.DELIVERED
    assert sender.code is not None
    verified = await client.post(
        f"/api/v1/auth/email-challenges/{challenge.id}/verify",
        json={"code": sender.code},
        headers=await write_headers(client),
    )
    assert verified.status_code == HTTPStatus.OK


async def publish(engine: AsyncEngine, version: str = "synthetic-test-v1") -> None:
    async with async_sessionmaker(engine).begin() as session:
        for kind in ("terms", "privacy"):
            session.add(
                PolicyDocumentRecord(
                    id=uuid4(),
                    kind=kind,
                    version=version,
                    title=f"Synthetic test {kind}",
                    content="Synthetic test document, not production legal text.",
                    published_at=datetime.now(UTC) - timedelta(days=1),
                )
            )


async def test_explicit_registration_http_stores_actual_context_and_bootstraps_receipt(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verify_student(browser, identity_engine)
    client = browser.client
    initial = IdentityResponse.model_validate((await client.get("/api/v1/me")).json())
    assert initial.registration is None
    await publish(identity_engine)
    document = await client.get("/api/v1/policies/terms")
    assert document.status_code == HTTPStatus.OK
    assert (
        PublishedPolicyResponse.model_validate(document.json()).reference.version
        == "synthetic-test-v1"
    )
    context_headers = await write_headers(client)
    response = await client.post("/api/v1/me/registration-context", headers=context_headers)
    assert response.status_code == HTTPStatus.CREATED
    context = RegistrationContextResponse.model_validate(response.json())
    assert context.surface.value == "onboarding_completion"
    assert "Terms of Use" in context.notice_text
    assert (
        await client.post("/api/v1/me/registration-context", headers=context_headers)
    ).json() == response.json()
    assert (
        IdentityResponse.model_validate((await client.get("/api/v1/me")).json()).registration
        is None
    )
    headers = await write_headers(client)
    cookie = client.cookies.get(SESSION_COOKIE)
    assert cookie is not None
    await ready_setup(identity_engine, SessionCredential(cookie))
    completed = await client.post(
        "/api/v1/me/registration", json={"context_id": str(context.id)}, headers=headers
    )
    assert completed.status_code == HTTPStatus.OK
    receipt = RegistrationReceiptResponse.model_validate(completed.json())
    assert receipt.notice_text == context.notice_text
    assert receipt.terms == context.terms
    assert receipt.privacy == context.privacy
    assert (
        await client.post(
            "/api/v1/me/registration", json={"context_id": str(context.id)}, headers=headers
        )
    ).json() == completed.json()
    actual = IdentityResponse.model_validate((await client.get("/api/v1/me")).json())
    assert actual.registration == receipt
    assert actual.capabilities.can_use_student_features
    status = PolicyStatusResponse.model_validate(
        (await client.get("/api/v1/me/policy-status")).json()
    )
    assert status.receipt == receipt
    await publish(identity_engine, "synthetic-test-v2")
    updated = PolicyStatusResponse.model_validate(
        (await client.get("/api/v1/me/policy-status")).json()
    )
    assert updated.receipt == receipt
    assert updated.current_terms is not None
    assert updated.current_terms.version == "synthetic-test-v2"
    assert (
        IdentityResponse.model_validate((await client.get("/api/v1/me")).json()).registration
        == receipt
    )
    repeated_context = await client.post(
        "/api/v1/me/registration-context", headers=await write_headers(client)
    )
    assert repeated_context.status_code == HTTPStatus.CONFLICT
    assert repeated_context.json()["code"] == "registration_already_completed"
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(RegistrationReceiptRecord))
        ).one() == 1


async def test_registration_requires_verified_identity_real_documents_and_csrf(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    client = browser.client
    headers = {"Idempotency-Key": str(uuid4())}
    assert (
        await client.post("/api/v1/me/registration-context", headers=headers)
    ).status_code == HTTPStatus.UNAUTHORIZED
    assert (await client.get("/api/v1/me/policy-status")).status_code == HTTPStatus.UNAUTHORIZED
    await login(client)
    unverified = await client.post(
        "/api/v1/me/registration-context", headers=await write_headers(client)
    )
    assert unverified.status_code == HTTPStatus.FORBIDDEN
    await verify_student(browser, identity_engine)
    missing = await client.post(
        "/api/v1/me/registration-context", headers=await write_headers(client)
    )
    assert missing.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert missing.json()["code"] == "registration_documents_unavailable"
    await publish(identity_engine)
    denied = await client.post(
        "/api/v1/me/registration-context", headers={"Idempotency-Key": str(uuid4())}
    )
    assert denied.status_code == HTTPStatus.FORBIDDEN
    absent = await client.post(
        "/api/v1/me/registration",
        json={"context_id": str(uuid4())},
        headers=await write_headers(client),
    )
    assert absent.status_code == HTTPStatus.CONFLICT
    assert absent.json()["code"] == "registration_context_unavailable"


async def test_policy_read_and_registration_input_do_not_fabricate_consent(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    client = browser.client
    assert (await client.get("/api/v1/policies/terms")).status_code == HTTPStatus.NOT_FOUND
    await publish(identity_engine)
    assert (
        await client.get("/api/v1/policies/privacy", params={"version": "synthetic-test-v1"})
    ).status_code == HTTPStatus.OK
    await verify_student(browser, identity_engine)
    invalid = await client.post(
        "/api/v1/me/registration",
        json={"context_id": str(uuid4()), "analytics_opt_in": True},
        headers=await write_headers(client),
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    extra_body = await client.post(
        "/api/v1/me/registration-context",
        json={"accepted": True},
        headers=await write_headers(client),
    )
    assert extra_body.status_code == HTTPStatus.BAD_REQUEST
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(RegistrationReceiptRecord))
        ).one() == 0
