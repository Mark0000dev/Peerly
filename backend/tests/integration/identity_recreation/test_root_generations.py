"""Actual repeated browser deletion/login/mail proof; no prior business-data restoration."""

from datetime import datetime
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.email_delivery import DeliverVerificationEmail, DeliveryStep
from studymate.application.identity.sessions import SessionCredential
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.domain.messaging import ConfirmedMessage
from studymate.infrastructure.persistence.email_delivery import SqlEmailWorkerUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.profile_models import ProfileRevisionRecord
from studymate.infrastructure.persistence.registration_models import RegistrationReceiptRecord
from studymate.infrastructure.security.email_vault import AeadEmailVault
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.identity import IdentityResponse
from tests.integration.http_identity import BrowserHarness, login, write_headers
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.test_message_commands import Chat, chat
from tests.integration.test_registration_http import Sender

pytestmark = pytest.mark.integration


async def delete_current(browser: BrowserHarness) -> UUID:
    client = browser.client
    headers = await write_headers(client)
    workflow = await client.post("/api/v1/me/deletion-workflows", json={}, headers=headers)
    assert workflow.status_code == HTTPStatus.OK
    identifier = UUID(workflow.json()["workflow_id"])
    deleted = await client.post(
        "/api/v1/me/deletion", json={"workflow_id": str(identifier)}, headers=headers
    )
    assert deleted.status_code == HTTPStatus.OK
    assert (await client.get("/api/v1/me")).status_code == HTTPStatus.UNAUTHORIZED
    return identifier


async def fresh_mail_proof(
    browser: BrowserHarness, engine: AsyncEngine, email: str
) -> tuple[UUID, str]:
    client = browser.client
    challenge = await client.post(
        "/api/v1/auth/email-challenges", json={"email": email}, headers=await write_headers(client)
    )
    assert challenge.status_code == HTTPStatus.ACCEPTED
    identifier = UUID(challenge.json()["id"])
    sender = Sender()
    worker = DeliverVerificationEmail(
        SqlEmailWorkerUnitOfWork(async_sessionmaker(engine)),
        sender,
        AeadEmailVault(bytes.fromhex("03" * 32), bytes.fromhex("01" * 32)),
    )
    assert await worker() == DeliveryStep.DELIVERED
    assert sender.code is not None
    result = await client.post(
        f"/api/v1/auth/email-challenges/{identifier}/verify",
        json={"code": sender.code},
        headers=await write_headers(client),
    )
    assert result.status_code == HTTPStatus.OK
    assert result.json()["verified_at"]
    return identifier, sender.code


async def test_three_generations_retain_all_history_but_require_new_proof_and_registration(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    original = await chat(identity_engine)
    operation = await original.send()(original.command())
    assert operation.message is not None
    message = operation.message
    async with original.api.sessions.begin() as session:
        at = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(at, datetime)
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=original.sender.id,
                issuer=GOOGLE_ISSUER,
                subject="subject",
                created_at=at,
            )
        )
        binding = await session.get(InstitutionalBindingRecord, original.sender.id)
        assert binding is not None
        email = binding.email
    client = browser.client
    await login(client)
    assert (
        IdentityResponse.model_validate((await client.get("/api/v1/me")).json()).account_id
        == original.sender.id
    )
    retired_cookie = client.cookies.get(SESSION_COOKIE)
    assert retired_cookie is not None
    old_workflow = await delete_current(browser)
    generations = [original.sender.id]
    stale_challenge: tuple[UUID, str] | None = None
    for turn in range(2):
        fresh = await fresh_identity(browser, identity_engine, generations)
        generations.append(fresh.account_id)
        wrong_workflow = await client.post(
            "/api/v1/me/deletion",
            json={"workflow_id": str(old_workflow)},
            headers=await write_headers(client),
        )
        assert wrong_workflow.status_code == HTTPStatus.NOT_FOUND
        if stale_challenge is not None:
            old_id, old_code = stale_challenge
            replay = await client.post(
                f"/api/v1/auth/email-challenges/{old_id}/verify",
                json={"code": old_code},
                headers=await write_headers(client),
            )
            assert replay.status_code == HTTPStatus.NOT_FOUND
        stale_challenge = await fresh_mail_proof(browser, identity_engine, email)
        assert (
            IdentityResponse.model_validate(
                (await client.get("/api/v1/me")).json()
            ).membership_status
            == "verified"
        )
        if turn == 0:
            credential = client.cookies.get(SESSION_COOKIE)
            assert credential is not None
            await ready_setup(identity_engine, SessionCredential(credential))
            context = await client.post(
                "/api/v1/me/registration-context", headers=await write_headers(client)
            )
            assert context.status_code == HTTPStatus.CREATED
            registered = await client.post(
                "/api/v1/me/registration",
                json={"context_id": context.json()["id"]},
                headers=await write_headers(client),
            )
            assert registered.status_code == HTTPStatus.OK
            assert (
                await client.get(f"/api/v1/conversations/{original.conversation_id}")
            ).status_code == HTTPStatus.NOT_FOUND
            assert (await client.get("/api/v1/conversations")).json()["conversations"] == []
            await delete_current(browser)
    await assert_retained_generations(original, message, generations, email)
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, retired_cookie)
    assert (await client.get("/api/v1/me")).status_code == HTTPStatus.UNAUTHORIZED


async def assert_retained_generations(
    original: Chat, message: ConfirmedMessage, generations: list[UUID], email: str
) -> None:
    async with original.api.sessions() as session:
        links = tuple(
            await session.scalars(
                select(ExternalIdentityRecord).where(ExternalIdentityRecord.subject == "subject")
            )
        )
        assert {link.account_id for link in links} == set(generations)
        assert sum(link.retired_at is None for link in links) == 1
        bindings = tuple(
            await session.scalars(
                select(InstitutionalBindingRecord).where(InstitutionalBindingRecord.email == email)
            )
        )
        assert {binding.account_id for binding in bindings} == set(generations)
        assert sum(binding.retired_at is None for binding in bindings) == 1
        retained_message = await session.get(MessageRecord, message.id)
        assert retained_message is not None
        assert retained_message.conversation_id == original.conversation_id
        receipts = tuple(
            await session.scalars(
                select(RegistrationReceiptRecord).where(
                    RegistrationReceiptRecord.account_id.in_(generations)
                )
            )
        )
        assert {receipt.account_id for receipt in receipts} == set(generations[:2])
        old_sessions = tuple(
            await session.scalars(
                select(SessionRecord).where(SessionRecord.account_id.in_(generations[:2]))
            )
        )
        assert all(row.revoked_at is not None for row in old_sessions)
        active = await session.get(AccountRecord, generations[-1])
        assert active is not None
        assert active.deleted_at is None


async def fresh_identity(
    browser: BrowserHarness, engine: AsyncEngine, generations: list[UUID]
) -> IdentityResponse:
    await login(browser.client)
    fresh = IdentityResponse.model_validate((await browser.client.get("/api/v1/me")).json())
    assert fresh.account_id not in generations
    assert fresh.membership_status == "unverified"
    assert fresh.registration is None
    assert not fresh.capabilities.can_use_student_features
    async with async_sessionmaker(engine)() as session:
        assert not tuple(
            await session.scalars(
                select(ProfileRevisionRecord).where(
                    ProfileRevisionRecord.account_id == fresh.account_id
                )
            )
        )
    return fresh
