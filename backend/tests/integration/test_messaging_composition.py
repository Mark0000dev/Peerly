from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.infrastructure.persistence.chat_participants import read_chat_participants
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.conversation_http_fixture import accepted_conversation
from tests.integration.http_identity import BrowserHarness, write_headers

pytestmark = pytest.mark.integration


async def test_actual_bootstrap_text_send_history_cancel_and_owned_outcome_truth(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    client_id = str(uuid4())
    path = f"{owned.prefix}/message-operations/{client_id}"
    unknown = await browser.client.get(path)
    assert unknown.status_code == HTTPStatus.OK
    assert unknown.json()["outcome"] == "unobserved"
    assert "not_sent" not in unknown.text
    body = {"client_message_id": client_id, "text": "  Preserved private text\n second line  "}
    headers = await write_headers(browser.client)
    sent = await browser.client.post(f"{owned.prefix}/messages", json=body, headers=headers)
    assert sent.status_code == HTTPStatus.OK
    assert sent.json()["outcome"] == "confirmed"
    assert sent.json()["message"]["text"] == body["text"]
    assert (
        await browser.client.post(f"{owned.prefix}/messages", json=body, headers=headers)
    ).json() == sent.json()
    assert (await browser.client.get(path)).json() == sent.json()
    cancel = await browser.client.post(
        f"{path}/cancel", headers=await write_headers(browser.client)
    )
    assert cancel.status_code == HTTPStatus.OK
    assert cancel.json() == sent.json()
    history = await browser.client.get(f"{owned.prefix}/messages")
    assert history.status_code == HTTPStatus.OK
    assert history.json()["messages"] == [sent.json()["message"]]
    assert history.headers["cache-control"] == "private, no-store"
    assert history.headers["x-request-id"]
    cancelled_id = str(uuid4())
    cancelled = await browser.client.post(
        f"{owned.prefix}/message-operations/{cancelled_id}/cancel",
        headers=await write_headers(browser.client),
    )
    assert cancelled.status_code == HTTPStatus.OK
    assert cancelled.json()["outcome"] == "cancelled"
    late = await browser.client.post(
        f"{owned.prefix}/messages",
        json={"client_message_id": cancelled_id, "text": "Delayed explicit send"},
        headers=await write_headers(browser.client),
    )
    assert late.status_code == HTTPStatus.OK
    assert late.json() == cancelled.json()
    assert len((await browser.client.get(f"{owned.prefix}/messages")).json()["messages"]) == 1


async def test_actual_chat_current_identity_and_display_avatar_remain_available_while_hidden(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    before = await browser.client.get(f"{owned.prefix}/participant")
    assert before.status_code == HTTPStatus.OK
    assert before.json()["state"] == "available"
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.actors.peer.credential.value)
    hidden = await browser.client.put(
        "/api/v1/me/visibility",
        json={"hidden": True, "expected_version": 1},
        headers=await write_headers(browser.client),
    )
    assert hidden.status_code == HTTPStatus.OK
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owned.actors.viewer.credential.value)
    assert (await browser.client.get(f"{owned.prefix}/participant")).json() == before.json()
    async with async_sessionmaker(identity_engine, expire_on_commit=False)() as session:
        source = (await read_chat_participants(session, (owned.actors.peer.id,)))[
            owned.actors.peer.id
        ]
    assert source.photo_reference is not None
    display = b"synthetic-processed-jpeg-display"
    browser.storage.retained[source.photo_reference] = display
    avatar = await browser.client.get(f"{owned.prefix}/participant/avatar/{source.photo_version}")
    assert avatar.status_code == HTTPStatus.OK
    assert avatar.content == display
    assert avatar.headers["content-type"] == "image/jpeg"
    assert avatar.headers["x-content-type-options"] == "nosniff"
    sent = await browser.client.post(
        f"{owned.prefix}/messages",
        json={"client_message_id": str(uuid4()), "text": "Existing chat remains usable"},
        headers=await write_headers(browser.client),
    )
    assert sent.status_code == HTTPStatus.OK
    assert sent.json()["outcome"] == "confirmed"


@pytest.mark.parametrize("cancel", [False, True])
async def test_bootstrap_message_commands_have_physical_body_bounds_and_safe_errors(
    browser: BrowserHarness,
    cancel: bool,
) -> None:
    prefix = f"/api/v1/conversations/{uuid4()}"
    path = f"{prefix}/message-operations/{uuid4()}/cancel" if cancel else f"{prefix}/messages"
    large = await browser.client.post(
        path, content=b"x" * 8193, headers={"Content-Type": "application/json"}
    )
    assert large.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert large.json()["code"] == "command_body_rejected"
    assert large.json()["request_id"] == large.headers["x-request-id"]
    assert "x" * 100 not in large.text
    small = await browser.client.post(
        path,
        content=b"null",
        headers={"Content-Type": "application/json" if cancel else "text/plain"},
    )
    assert small.status_code == (
        HTTPStatus.BAD_REQUEST if cancel else HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    )
    if cancel:
        empty = await browser.client.post(path, headers={"Idempotency-Key": str(uuid4())})
        assert empty.status_code == HTTPStatus.UNAUTHORIZED


async def test_bootstrap_message_actor_origin_and_source_fields_are_not_client_authority(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owned = await accepted_conversation(browser, identity_engine)
    path = f"{owned.prefix}/messages"
    body = {"client_message_id": str(uuid4()), "text": "PRIVATE SYNTHETIC CONTENT"}
    headers = await write_headers(browser.client)
    headers["Origin"] = "https://foreign.test"
    denied = await browser.client.post(path, json=body, headers=headers)
    assert denied.status_code == HTTPStatus.FORBIDDEN
    assert denied.json()["request_id"] == denied.headers["x-request-id"]
    for extra in ({"actor_id": str(owned.actors.peer.id)}, {"system_prompt": "forbidden"}):
        invalid = await browser.client.post(
            path, json={**body, **extra}, headers=await write_headers(browser.client)
        )
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body["text"] not in invalid.text
