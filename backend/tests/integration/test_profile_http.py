from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.domain.profiles import OnboardingTask
from studymate.presentation.profile_models import (
    OwnProfileResponse,
    ProfileReferenceResponse,
    ProfileRevisionResponse,
)
from tests.integration.http_identity import BrowserHarness, login, verified, write_headers

pytestmark = pytest.mark.integration


def payload(*, version: int = 0) -> dict[str, object]:
    return {
        "display_name": "  Synthetic   Student  ",
        "about": " Private context ",
        "programme": " Synthetic programme ",
        "year_label": " Year 1 ",
        "languages": [" EN ", "ms"],
        "task": "find_help",
        "expected_version": version,
    }


async def test_profile_http_draft_resume_normalization_original_replay_and_conflict(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    client = browser.client
    initial = OwnProfileResponse.model_validate((await client.get("/api/v1/me/profile")).json())
    assert initial.profile is None
    assert initial.photo is None
    headers = await write_headers(client)
    saved = await client.put("/api/v1/me/profile", json=payload(), headers=headers)
    assert saved.status_code == HTTPStatus.OK
    first = ProfileRevisionResponse.model_validate(saved.json())
    assert first.display_name == "Synthetic Student"
    assert first.languages == ("en", "ms")
    assert saved.headers["cache-control"] == "no-store"
    later = await client.put(
        "/api/v1/me/profile",
        json={
            **payload(version=first.version),
            "display_name": "Changed synthetic",
            "task": "offer_help",
        },
        headers=await write_headers(client),
    )
    assert later.status_code == HTTPStatus.OK
    second = ProfileRevisionResponse.model_validate(later.json())
    assert second.version == first.version + 1
    assert second.task == OnboardingTask.OFFER_HELP
    assert (
        await client.put("/api/v1/me/profile", json=payload(), headers=headers)
    ).json() == first.model_dump(mode="json")
    resumed = OwnProfileResponse.model_validate((await client.get("/api/v1/me/profile")).json())
    assert resumed.profile == second
    stale = await client.put(
        "/api/v1/me/profile", json=payload(), headers=await write_headers(client)
    )
    assert stale.status_code == HTTPStatus.CONFLICT
    assert stale.json()["code"] == "profile_version_conflict"
    assert stale.json()["recovery"]["current_version"] == second.version
    reused = await client.put(
        "/api/v1/me/profile", json={**payload(), "display_name": "Other synthetic"}, headers=headers
    )
    assert reused.json()["code"] == "idempotency_conflict"


async def test_profile_reference_and_unknown_language_are_server_owned(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await verified(browser, identity_engine)
    client = browser.client
    response = await client.get("/api/v1/profile-reference-data")
    options = ProfileReferenceResponse.model_validate(response.json())
    assert {"en", "ms", "zh", "ta", "ar"} <= {item.code for item in options.languages}
    assert options.university == "APU Malaysia"
    assert options.max_languages > 0
    unsupported = await client.put(
        "/api/v1/me/profile",
        json={**payload(), "languages": ["zz"]},
        headers=await write_headers(client),
    )
    assert unsupported.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert unsupported.json()["code"] == "profile_language_unsupported"
    assert unsupported.json()["errors"][0]["path"] == ["languages"]


@pytest.mark.parametrize(
    "change",
    [
        {"display_name": " X "},
        {"languages": ["en", "EN"]},
        {"programme": "private\x00invalid"},
        {"expected_version": True},
    ],
)
async def test_profile_validation_has_field_paths_without_private_echo(
    browser: BrowserHarness, identity_engine: AsyncEngine, change: dict[str, object]
) -> None:
    await verified(browser, identity_engine)
    response = await browser.client.put(
        "/api/v1/me/profile",
        json={**payload(), **change},
        headers=await write_headers(browser.client),
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["errors"]
    assert "private" not in response.text


async def test_profile_and_reference_require_verified_identity_and_write_guards(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    client = browser.client
    assert (await client.get("/api/v1/me/profile")).status_code == HTTPStatus.UNAUTHORIZED
    assert (
        await client.get("/api/v1/profile-reference-data")
    ).status_code == HTTPStatus.UNAUTHORIZED
    await login(client)
    assert (await client.get("/api/v1/me/profile")).status_code == HTTPStatus.FORBIDDEN
    assert (await client.get("/api/v1/profile-reference-data")).status_code == HTTPStatus.FORBIDDEN
    await verified(browser, identity_engine)
    headers = await write_headers(client)
    response = await client.put(
        "/api/v1/me/profile", json=payload(), headers={**headers, "Origin": "https://foreign.test"}
    )
    assert response.json()["code"] == "origin_denied"
    client.cookies.clear()
    unauthenticated = await client.put(
        "/api/v1/me/profile", json=payload(), headers={"Idempotency-Key": str(uuid4())}
    )
    assert unauthenticated.status_code == HTTPStatus.UNAUTHORIZED
