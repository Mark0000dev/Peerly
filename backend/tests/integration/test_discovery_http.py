from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.domain.study_context import HelpSubject, HelpSubjects
from studymate.presentation.discovery_models import DiscoveryPageResponse, PrivatePassResponse
from tests.integration.catalogue_fixture import subject
from tests.integration.discovery_fixture import canonical_goal
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.people_fixture import PeopleHarness
from tests.integration.people_fixture import mounted as people_mounted
from tests.integration.test_help_subjects import command as help_command
from tests.integration.test_help_subjects import services as help_services

pytestmark = pytest.mark.integration


async def mounted(browser: BrowserHarness, engine: AsyncEngine) -> PeopleHarness:
    actors = await people_mounted(browser, engine)
    known = await subject(engine)
    await canonical_goal(engine, actors.viewer, known.id)
    save_help, _ = help_services(engine)
    await save_help(help_command(actors.peer, HelpSubjects((HelpSubject(known.id),))))
    return actors


async def snapshot(browser: BrowserHarness) -> DiscoveryPageResponse:
    response = await browser.client.get("/api/v1/discovery", params={"mode": "find_help"})
    assert response.status_code == HTTPStatus.OK
    return DiscoveryPageResponse.model_validate(response.json())


async def test_actual_http_deck_pass_undo_and_original_replay(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    actors = await mounted(browser, identity_engine)
    first = await snapshot(browser)
    assert [person.id for person in first.people] == [actors.peer.id]
    assert first.people[0].relevance.reason.value == "can_help"
    assert first.people[0].own_pass.version == 0
    assert first.context is not None
    context = first.context.model_dump(mode="json")
    assert "account_id" not in context
    body: dict[str, object] = {"context": context, "passed": True, "expected_version": 0}
    path = f"/api/v1/discovery/passes/{actors.peer.id}"
    headers = await write_headers(browser.client)
    sent = await browser.client.put(path, json=body, headers=headers)
    assert sent.status_code == HTTPStatus.OK
    assert sent.headers["cache-control"] == "no-store"
    saved = PrivatePassResponse.model_validate(sent.json())
    after = await snapshot(browser)
    assert not after.people
    assert after.undo_pass == saved
    assert after.empty_reason is not None
    review = await browser.client.get(
        "/api/v1/discovery", params={"mode": "find_help", "view": "passed"}
    )
    assert DiscoveryPageResponse.model_validate(review.json()).people[0].own_pass == saved
    undo = await browser.client.put(
        path,
        json={**body, "passed": False, "expected_version": saved.version, "undo": True},
        headers=await write_headers(browser.client),
    )
    assert undo.status_code == HTTPStatus.OK
    current = PrivatePassResponse.model_validate(undo.json())
    assert not current.passed
    assert current.version == saved.version + 1
    assert (
        PrivatePassResponse.model_validate(
            (await browser.client.put(path, json=body, headers=headers)).json()
        )
        == saved
    )
    assert (await snapshot(browser)).people[0].own_pass == current


async def test_http_private_context_cannot_select_actor_or_another_goal(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    actors = await mounted(browser, identity_engine)
    page = await snapshot(browser)
    assert page.context is not None
    context = page.context.model_dump(mode="json")
    path = f"/api/v1/discovery/passes/{actors.peer.id}"
    body: dict[str, object] = {"context": context, "passed": True, "expected_version": 0}
    for changed in (
        {**body, "actor_id": str(actors.peer.id)},
        {**body, "context": {**context, "account_id": str(actors.peer.id)}},
        {**body, "passed": "true"},
        {**body, "expected_version": True},
        {**body, "undo": True},
    ):
        response = await browser.client.put(
            path, json=changed, headers=await write_headers(browser.client)
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    stale = await browser.client.put(
        path,
        json={**body, "context": {**context, "goal_id": str(uuid4())}},
        headers=await write_headers(browser.client),
    )
    assert stale.status_code == HTTPStatus.CONFLICT
    assert stale.json()["code"] == "discovery_context_changed"


async def test_http_cursor_and_cookie_recovery_are_safe(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    await mounted(browser, identity_engine)
    invalid = await browser.client.get(
        "/api/v1/discovery", params={"mode": "find_help", "cursor": "!private"}
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert invalid.json()["code"] == "invalid_cursor"
    assert "!private" not in invalid.text
    assert invalid.headers["x-request-id"] == invalid.json()["request_id"]
    browser.client.cookies.clear()
    missing = await browser.client.get("/api/v1/discovery", params={"mode": "find_help"})
    assert missing.status_code == HTTPStatus.UNAUTHORIZED


async def test_http_pass_origin_and_immutable_intent_guards(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    actors = await mounted(browser, identity_engine)
    page = await snapshot(browser)
    assert page.context is not None
    body: dict[str, object] = {
        "context": page.context.model_dump(mode="json"),
        "passed": True,
        "expected_version": 0,
    }
    headers = await write_headers(browser.client)
    path = f"/api/v1/discovery/passes/{actors.peer.id}"
    no_origin = {key: value for key, value in headers.items() if key.lower() != "origin"}
    assert (
        await browser.client.put(path, json=body, headers=no_origin)
    ).status_code == HTTPStatus.FORBIDDEN
    accepted = await browser.client.put(path, json=body, headers=headers)
    assert accepted.status_code == HTTPStatus.OK
    changed = await browser.client.put(path, json={**body, "passed": False}, headers=headers)
    assert changed.status_code == HTTPStatus.CONFLICT
    assert changed.json()["code"] == "idempotency_conflict"


async def test_http_pass_body_and_stale_revision_recovery_are_bounded(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    actors = await mounted(browser, identity_engine)
    page = await snapshot(browser)
    assert page.context is not None
    path = f"/api/v1/discovery/passes/{actors.peer.id}"
    headers = await write_headers(browser.client)
    assert (
        await browser.client.put(
            path, content="{}", headers={**headers, "content-type": "text/plain"}
        )
    ).status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    large = await browser.client.put(
        path, content="x" * 8193, headers={**headers, "content-type": "application/json"}
    )
    assert large.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert large.json()["code"] == "command_body_rejected"
    body: dict[str, object] = {
        "context": page.context.model_dump(mode="json"),
        "passed": True,
        "expected_version": 0,
    }
    saved = await browser.client.put(path, json=body, headers=headers)
    assert saved.status_code == HTTPStatus.OK
    stale = await browser.client.put(path, json=body, headers=await write_headers(browser.client))
    assert stale.status_code == HTTPStatus.CONFLICT
    assert stale.json()["code"] == "pass_version_conflict"
    assert stale.json()["recovery"]["current_version"] == 1


async def test_http_absent_undo_is_a_truthful_conflict(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    actors = await mounted(browser, identity_engine)
    page = await snapshot(browser)
    assert page.context is not None
    body: dict[str, object] = {
        "context": page.context.model_dump(mode="json"),
        "passed": False,
        "expected_version": 0,
        "undo": True,
    }
    unavailable = await browser.client.put(
        f"/api/v1/discovery/passes/{actors.peer.id}",
        json=body,
        headers=await write_headers(browser.client),
    )
    assert unavailable.status_code == HTTPStatus.CONFLICT
    assert unavailable.json()["code"] == "pass_undo_unavailable"
