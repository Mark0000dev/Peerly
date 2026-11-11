from http import HTTPStatus

import pytest
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.sessions import SessionCredential
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.identity import IdentityResponse
from studymate.presentation.onboarding_models import (
    OnboardingStatusResponse,
    ProfileVisibilityResponse,
)
from tests.integration.http_identity import BrowserHarness, verified, write_headers
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.registration_fixture import documents

pytestmark = pytest.mark.integration


async def test_actual_onboarding_http_completes_once_then_visibility_preserves_chat_capability(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    client = browser.client
    await verified(browser, identity_engine)
    draft = await client.get("/api/v1/me/onboarding")
    assert draft.status_code == HTTPStatus.OK
    assert draft.headers["cache-control"] == "no-store"
    status = OnboardingStatusResponse.model_validate(draft.json())
    assert status.visibility is None
    assert not status.registered
    assert not status.setup_complete
    assert tuple(item.value for item in status.setup_requirements) == (
        "display_name",
        "photo",
        "study_goal",
    )
    await documents(identity_engine)
    context = await client.post(
        "/api/v1/me/registration-context", headers=await write_headers(client)
    )
    assert context.status_code == HTTPStatus.CREATED
    headers = await write_headers(client)
    request = {"context_id": context.json()["id"]}
    incomplete = await client.post("/api/v1/me/registration", json=request, headers=headers)
    assert incomplete.status_code == HTTPStatus.CONFLICT
    assert incomplete.json()["code"] == "onboarding_incomplete"
    assert incomplete.json()["errors"] == [
        {"path": ["onboarding", name], "code": "required"}
        for name in ("display_name", "photo", "study_goal")
    ]
    credential = client.cookies.get(SESSION_COOKIE)
    assert credential is not None
    await ready_setup(identity_engine, SessionCredential(credential))
    prepared = OnboardingStatusResponse.model_validate(
        (await client.get("/api/v1/me/onboarding")).json()
    )
    assert prepared.capabilities.can_complete_registration
    assert not prepared.capabilities.can_discover
    assert (
        await client.post("/api/v1/me/registration", json=request, headers=headers)
    ).status_code == HTTPStatus.OK
    active = OnboardingStatusResponse.model_validate(
        (await client.get("/api/v1/me/onboarding")).json()
    )
    assert active.setup_complete
    assert active.registered
    assert active.visibility is not None
    assert active.capabilities.can_discover
    assert IdentityResponse.model_validate(
        (await client.get("/api/v1/me")).json()
    ).capabilities.can_use_student_features
    hide_headers = await write_headers(client)
    hide_body = {"hidden": True, "expected_version": active.visibility.version}
    response = await client.put("/api/v1/me/visibility", json=hide_body, headers=hide_headers)
    assert response.status_code == HTTPStatus.OK
    hidden = ProfileVisibilityResponse.model_validate(response.json())
    assert hidden.hidden
    assert hidden.completed_at == active.visibility.completed_at
    assert (
        await client.put("/api/v1/me/visibility", json=hide_body, headers=hide_headers)
    ).json() == response.json()
    current = OnboardingStatusResponse.model_validate(
        (await client.get("/api/v1/me/onboarding")).json()
    )
    assert current.capabilities.can_access_existing_chats
    assert not current.capabilities.can_make_new_contacts
    stale = await client.put(
        "/api/v1/me/visibility", json=hide_body, headers=await write_headers(client)
    )
    assert stale.status_code == HTTPStatus.CONFLICT
    assert stale.json()["recovery"]["current_version"] == hidden.version
    restored = await client.put(
        "/api/v1/me/visibility",
        json={"hidden": False, "expected_version": hidden.version},
        headers=await write_headers(client),
    )
    assert restored.status_code == HTTPStatus.OK
    assert not ProfileVisibilityResponse.model_validate(restored.json()).hidden


async def test_visibility_http_requires_cookie_origin_csrf_and_strict_command(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    client = browser.client
    assert (await client.get("/api/v1/me/onboarding")).status_code == HTTPStatus.UNAUTHORIZED
    await verified(browser, identity_engine)
    command = {"hidden": True, "expected_version": 1}
    assert (
        await client.put(
            "/api/v1/me/visibility", json=command, headers={"Idempotency-Key": "synthetic-key"}
        )
    ).status_code == HTTPStatus.FORBIDDEN
    headers = await write_headers(client)
    assert (
        await client.put("/api/v1/me/visibility", json=command, headers=headers)
    ).status_code == HTTPStatus.FORBIDDEN
    assert (
        await client.put(
            "/api/v1/me/visibility", json={"hidden": "true", "expected_version": 1}, headers=headers
        )
    ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert (
        await client.put(
            "/api/v1/me/visibility",
            json={"hidden": True, "expected_version": True},
            headers=headers,
        )
    ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert (
        await client.put("/api/v1/me/visibility", content="hidden=true", headers=headers)
    ).status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


@pytest.mark.parametrize("state", ["banned", "deleted"])
async def test_onboarding_read_denies_restricted_identity(
    browser: BrowserHarness, identity_engine: AsyncEngine, state: str
) -> None:
    account_id = await verified(browser, identity_engine)
    async with async_sessionmaker(identity_engine).begin() as session:
        column = AccountRecord.banned_at if state == "banned" else AccountRecord.deleted_at
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == account_id)
            .values({column: func.clock_timestamp()})
        )
    response = await browser.client.get("/api/v1/me/onboarding")
    assert response.status_code == (
        HTTPStatus.FORBIDDEN if state == "banned" else HTTPStatus.UNAUTHORIZED
    )
    assert response.json()["request_id"]


async def test_activated_profile_http_rejects_clearing_display_name(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    client = browser.client
    credential = client.cookies.get(SESSION_COOKIE)
    assert credential is not None
    await ready_setup(identity_engine, SessionCredential(credential))
    await documents(identity_engine)
    context = await client.post(
        "/api/v1/me/registration-context", headers=await write_headers(client)
    )
    completed = await client.post(
        "/api/v1/me/registration",
        json={"context_id": context.json()["id"]},
        headers=await write_headers(client),
    )
    assert completed.status_code == HTTPStatus.OK
    invalid_name = await client.put(
        "/api/v1/me/profile",
        json={"display_name": None, "expected_version": 1},
        headers=await write_headers(client),
    )
    assert invalid_name.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert invalid_name.json()["code"] == "profile_name_required"
