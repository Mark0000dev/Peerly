from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.conversation_http_fixture import accepted_conversation
from tests.integration.http_identity import BrowserHarness, write_headers

pytestmark = pytest.mark.integration


async def test_actual_bootstrap_goal_sharing_is_explicit_immutable_context_and_not_a_human_message(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    path = f"{owned.prefix}/goal-shares"
    baseline = await browser.client.get(path)
    assert baseline.status_code == HTTPStatus.OK
    assert baseline.json()["current_context_version"] == 0
    assert baseline.json()["latest"] is None
    assert not baseline.json()["history"]
    goal = (await browser.client.get("/api/v1/me/goal")).json()["goal"]
    body = {
        "goal_id": goal["id"],
        "expected_goal_version": goal["version"],
        "expected_context_version": 0,
    }
    headers = await write_headers(browser.client)
    shared = await browser.client.post(path, json=body, headers=headers)
    assert shared.status_code == HTTPStatus.OK
    assert shared.json()["context_version"] == 1
    assert shared.json()["source"]["goal_id"] == goal["id"]
    assert (await browser.client.post(path, json=body, headers=headers)).json() == shared.json()
    history = await browser.client.get(path)
    assert history.json()["baseline"] == baseline.json()["baseline"]
    assert history.json()["latest"]["can_complete"]
    assert (await browser.client.get(f"{owned.prefix}/messages")).json()["messages"] == []
    completed = await browser.client.post(
        "/api/v1/me/goal/complete",
        json={"goal_id": goal["id"], "expected_version": goal["version"]},
        headers=await write_headers(browser.client),
    )
    assert completed.status_code == HTTPStatus.OK
    assert (await browser.client.post(path, json=body, headers=headers)).json() == shared.json()
    after = await browser.client.get(path)
    assert not after.json()["latest"]["can_complete"]
    assert after.json()["latest"]["source"] == shared.json()["source"]
    assert after.json()["baseline"]["context"] == baseline.json()["baseline"]["context"]
    assert (await browser.client.get(f"{owned.prefix}/messages")).json()["messages"] == []


async def test_actual_goal_share_only_accepts_owned_refs_and_has_shared_body_error_bounds(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    path = f"{owned.prefix}/goal-shares"
    large = await browser.client.post(
        path, content=b"x" * 8193, headers={"Content-Type": "application/json"}
    )
    assert large.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert large.json()["code"] == "command_body_rejected"
    assert large.json()["request_id"] == large.headers["x-request-id"]
    wrong_type = await browser.client.post(
        path, content=b"{}", headers={"Content-Type": "text/plain"}
    )
    assert wrong_type.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    goal = (await browser.client.get("/api/v1/me/goal")).json()["goal"]
    body = {
        "goal_id": goal["id"],
        "expected_goal_version": goal["version"],
        "expected_context_version": 0,
    }
    invalid = await browser.client.post(
        path,
        json={**body, "text": "PRIVATE CLIENT OVERRIDE", "actor_id": str(uuid4())},
        headers=await write_headers(browser.client),
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "PRIVATE CLIENT OVERRIDE" not in invalid.text
    conflict = await browser.client.post(
        path,
        json={**body, "expected_context_version": 99},
        headers=await write_headers(browser.client),
    )
    assert conflict.status_code == HTTPStatus.CONFLICT
    assert conflict.json()["code"] == "conversation_goal_context_changed"
