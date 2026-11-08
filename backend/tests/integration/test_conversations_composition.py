from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.conversation_http_fixture import accepted_conversation
from tests.integration.http_identity import BrowserHarness, write_headers

pytestmark = pytest.mark.integration


async def test_actual_conversation_details_and_explicit_read_ack_are_private_and_monotonic(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    initial = await browser.client.get(owned.prefix)
    assert initial.status_code == HTTPStatus.OK
    assert initial.json()["last_confirmed_sequence"] == 0
    assert initial.json()["read_position"] is None
    assert initial.json()["unread_count"] == 0
    assert initial.json()["can_send"]
    assert initial.headers["cache-control"] == "private, no-store"
    sent = await browser.client.post(
        f"{owned.prefix}/messages",
        json={"client_message_id": str(uuid4()), "text": "Private chat"},
        headers=await write_headers(browser.client),
    )
    assert sent.status_code == HTTPStatus.OK
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.actors.peer.credential.value)
    before = await browser.client.get(owned.prefix)
    assert before.json()["unread_count"] == 1
    assert before.json()["read_position"] is None
    assert (await browser.client.get(owned.prefix)).json() == before.json()
    headers = await write_headers(browser.client)
    ack = await browser.client.put(
        f"{owned.prefix}/read-position",
        json={"through_sequence": 1},
        headers=headers,
    )
    assert ack.status_code == HTTPStatus.OK
    assert ack.json()["through_sequence"] == 1
    assert (
        await browser.client.put(
            f"{owned.prefix}/read-position",
            json={"through_sequence": 1},
            headers=headers,
        )
    ).json() == ack.json()
    after = await browser.client.get(owned.prefix)
    assert after.json()["unread_count"] == 0
    assert after.json()["original_context"] == before.json()["original_context"]
    future = await browser.client.put(
        f"{owned.prefix}/read-position",
        json={"through_sequence": 2},
        headers=await write_headers(browser.client),
    )
    assert future.status_code == HTTPStatus.CONFLICT
    assert future.json()["code"] == "conversation_read_sequence_unavailable"
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.actors.viewer.credential.value)
    sender = await browser.client.get(owned.prefix)
    assert sender.json()["read_position"] is None
    assert "Private chat" not in sender.text
    assert "account_id" not in ack.json()


async def test_conversation_ack_uses_shared_bounds_and_cannot_claim_another_actor(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    path = f"{owned.prefix}/read-position"
    large = await browser.client.put(
        path,
        content=b"x" * 8193,
        headers={"content-type": "application/json"},
    )
    assert large.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    wrong = await browser.client.put(
        path,
        content=b"{}",
        headers={"content-type": "text/plain"},
    )
    assert wrong.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    for body in (
        {"through_sequence": True},
        {"through_sequence": 0},
        {"through_sequence": 1, "actor_id": str(uuid4())},
    ):
        invalid = await browser.client.put(
            path, json=body, headers=await write_headers(browser.client)
        )
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    missing = await browser.client.get(f"/api/v1/conversations/{uuid4()}")
    assert missing.status_code == HTTPStatus.NOT_FOUND
    assert missing.json()["request_id"] == missing.headers["x-request-id"]


async def test_actual_root_thread_list_has_real_preview_and_never_acknowledges_implicit_reading(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    initial = await browser.client.get("/api/v1/conversations")
    assert initial.status_code == HTTPStatus.OK
    assert initial.headers["cache-control"] == "private, no-store"
    assert initial.json()["next_cursor"] is None
    assert len(initial.json()["conversations"]) == 1
    first = initial.json()["conversations"][0]
    assert first["conversation_id"] == str(owned.conversation_id)
    assert first["last_message"] is None
    assert first["unread_count"] == 0
    assert first["activity_at"] == first["accepted_at"]
    sent = await browser.client.post(
        f"{owned.prefix}/messages",
        json={"client_message_id": str(uuid4()), "text": "Private actual thread preview"},
        headers=await write_headers(browser.client),
    )
    assert sent.status_code == HTTPStatus.OK
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.actors.peer.credential.value)
    received = await browser.client.get("/api/v1/conversations")
    row = received.json()["conversations"][0]
    assert row["last_message"] == sent.json()["message"]
    assert row["unread_count"] == 1
    assert row["original_context"] == first["original_context"]
    assert (await browser.client.get("/api/v1/conversations")).json() == received.json()
    assert (await browser.client.get(owned.prefix)).json()["read_position"] is None
    invalid = await browser.client.get(
        "/api/v1/conversations", params={"cursor": "private-invalid-token"}
    )
    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert invalid.json()["code"] == "invalid_conversation_cursor"
    assert "private-invalid-token" not in invalid.text
    assert "Private actual thread preview" not in invalid.text
    browser.client.cookies.clear()
    assert (
        await browser.client.get("/api/v1/conversations")
    ).status_code == HTTPStatus.UNAUTHORIZED
