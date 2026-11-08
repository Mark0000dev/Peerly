import asyncio
from http import HTTPStatus
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.types import Message, Scope

from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.change_fixture import drain, head_positions
from tests.integration.http_identity import BrowserHarness
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


async def test_root_exhausted_change_pool_leaves_identity_and_ai_pools_independent(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    owned = await chat(identity_engine)
    browser.client.cookies.set(SESSION_COOKIE, owned.recipient.credential.value)
    assert browser.change_engine.pool is not browser.ai_engine.pool
    assert browser.change_engine.pool is not identity_engine.pool
    assert browser.ai_engine.pool is not identity_engine.pool
    async with browser.change_engine.connect(), browser.change_engine.connect():
        async with asyncio.timeout(3):
            changes, identity, ai = await asyncio.gather(
                browser.client.get("/api/v1/events"),
                browser.client.get("/api/v1/me"),
                browser.client.get(f"/api/v1/ai/jobs/{uuid4()}"),
            )
    assert changes.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert changes.json()["code"] == "storage_unavailable"
    assert changes.headers["Retry-After"] == "1"
    assert changes.headers["X-Request-ID"] == changes.json()["request_id"]
    assert identity.status_code == HTTPStatus.OK
    assert ai.status_code == HTTPStatus.NOT_FOUND
    browser.client.cookies.clear()
    assert (await browser.client.get("/api/v1/events")).status_code == HTTPStatus.UNAUTHORIZED


async def test_root_owned_change_frame_releases_sql_and_revocation_closes_stream(
    browser: BrowserHarness, identity_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    owned = await chat(identity_engine)
    await drain(owned)
    baseline = (await head_positions(owned))[owned.recipient.id]
    command = owned.command()
    await owned.send()(command)
    await drain(owned)
    frames: list[bytes] = []
    headers: list[tuple[bytes, bytes]] = []
    statuses: list[int] = []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/api/v1/events",
        "raw_path": b"/api/v1/events",
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 1234),
        "server": ("app.test", 443),
        "headers": [
            (b"cookie", f"{SESSION_COOKIE}={owned.recipient.credential.value}".encode()),
            (b"last-event-id", str(baseline).encode()),
        ],
    }

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            statuses.append(message["status"])
            headers.extend(message["headers"])
        elif message["type"] == "http.response.body" and message.get("body"):
            frames.append(message["body"])
            async with owned.api.sessions.begin() as session:
                # A real NOWAIT lock proves no SQL lease spans this network send.
                assert (
                    await session.scalar(
                        select(AccountRecord.id)
                        .where(AccountRecord.id == owned.recipient.id)
                        .with_for_update(nowait=True)
                    )
                    == owned.recipient.id
                )
                await session.execute(
                    update(SessionRecord)
                    .where(SessionRecord.account_id == owned.recipient.id)
                    .values(revoked_at=func.clock_timestamp())
                )

    async with asyncio.timeout(5):
        await browser.app(scope, receive, send)
    assert statuses == [HTTPStatus.OK]
    assert len(frames) == 1
    assert frames[0].startswith(f"id: {baseline + 1}\nevent: resource.changed\n".encode())
    assert str(owned.conversation_id).encode() in frames[0]
    assert dict(headers)[b"cache-control"] == b"private, no-store"
    assert dict(headers)[b"x-request-id"]
    assert command.content.text is not None
    assert command.content.text not in frames[0].decode()
    assert command.content.text not in caplog.text
    assert owned.recipient.credential.value not in caplog.text
    assert owned.recipient.credential.value.encode() not in frames[0]
