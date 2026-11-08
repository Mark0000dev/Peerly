from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.test_discovery_http import mounted

pytestmark = pytest.mark.integration


async def test_real_bootstrap_requests_preview_send_read_ack_and_accept(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    actors = await mounted(browser, identity_engine)
    preview = await browser.client.post(
        "/api/v1/requests/preview",
        json={"person_id": str(actors.peer.id), "mode": "find_help"},
        headers=await write_headers(browser.client),
    )
    assert preview.status_code == HTTPStatus.OK
    assert preview.json()["outcome"] == "preview"
    body = {
        "person_id": str(actors.peer.id),
        "preview_id": preview.json()["preview_id"],
        "text": "Explicit synthetic reviewed request",
        "note": "Synthetic private separate note",
    }
    headers = await write_headers(browser.client)
    sent = await browser.client.post("/api/v1/requests", json=body, headers=headers)
    assert sent.status_code == HTTPStatus.OK
    assert sent.json()["outcome"] == "sent"
    assert (
        await browser.client.post("/api/v1/requests", json=body, headers=headers)
    ).json() == sent.json()
    request_id = sent.json()["request_id"]
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, actors.peer.credential.value)
    detail = await browser.client.get(f"/api/v1/requests/{request_id}")
    assert detail.status_code == HTTPStatus.OK
    assert detail.json()["request"]["unread"]
    assert detail.json()["text"] == body["text"]
    assert detail.headers["cache-control"] == "no-store"
    assert detail.headers["x-request-id"]
    ack = await browser.client.post(
        f"/api/v1/requests/{request_id}/viewed",
        json={"disclosure_id": detail.json()["disclosure_id"]},
        headers=await write_headers(browser.client),
    )
    assert ack.status_code == HTTPStatus.OK
    listed = await browser.client.get("/api/v1/requests", params={"box": "received"})
    assert listed.status_code == HTTPStatus.OK
    assert not listed.json()["requests"][0]["unread"]
    accepted = await browser.client.post(
        f"/api/v1/requests/{request_id}/accept",
        json={"person_id": str(actors.viewer.id), "expected_version": sent.json()["version"]},
        headers=await write_headers(browser.client),
    )
    assert accepted.status_code == HTTPStatus.OK
    assert accepted.json()["conversation_id"]
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, actors.viewer.credential.value)
    connected = await browser.client.post(
        "/api/v1/requests/preview",
        json={"person_id": str(actors.peer.id), "mode": "find_help"},
        headers=await write_headers(browser.client),
    )
    assert connected.status_code == HTTPStatus.OK
    assert connected.json()["outcome"] == "connected"
    assert connected.json()["conversation_id"] == accepted.json()["conversation_id"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/requests",
        "/api/v1/requests/preview",
        "/api/v1/requests/00000000-0000-0000-0000-000000000001/accept",
    ],
)
async def test_bootstrap_requests_apply_shared_body_bounds_and_safe_correlated_problems(
    browser: BrowserHarness, path: str
) -> None:
    too_large = await browser.client.post(
        path, content=b"x" * 8193, headers={"Content-Type": "application/json"}
    )
    assert too_large.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert too_large.json()["code"] == "command_body_rejected"
    assert too_large.json()["request_id"] == too_large.headers["x-request-id"]
    assert "x" * 100 not in too_large.text
    bad_type = await browser.client.post(
        path, content=b"{}", headers={"Content-Type": "text/plain"}
    )
    assert bad_type.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    assert bad_type.json()["code"] == "command_body_rejected"


async def test_bootstrap_requests_require_actor_cookie_and_reject_foreign_origin(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    response = await browser.client.get("/api/v1/requests")
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    actors = await mounted(browser, identity_engine)
    body = {"person_id": str(actors.peer.id), "mode": "find_help"}
    headers = await write_headers(browser.client)
    headers["Origin"] = "https://foreign.test"
    denied = await browser.client.post("/api/v1/requests/preview", json=body, headers=headers)
    assert denied.status_code == HTTPStatus.FORBIDDEN
    assert denied.json()["request_id"] == denied.headers["x-request-id"]
    unknown = await browser.client.get(f"/api/v1/requests/{uuid4()}")
    assert unknown.status_code == HTTPStatus.NOT_FOUND
    assert unknown.json()["code"] == "request_unavailable"
