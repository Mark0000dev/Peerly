import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.types import Message, Scope

from studymate.application.changes.reads import ReadChanges
from studymate.infrastructure.changes.reads import SqlChangeReadUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.changes.router import ChangeHttpServices, changes_router
from studymate.presentation.changes.stream import ChangeStreamPolicy
from tests.integration.change_fixture import drain, head_positions
from tests.integration.requests.fixture import HASHER
from tests.integration.test_message_commands import Chat, chat

pytestmark = pytest.mark.integration


@asynccontextmanager
async def application(owned: Chat) -> AsyncIterator[FastAPI]:
    app = FastAPI()
    app.include_router(
        changes_router(
            ChangeHttpServices(
                ReadChanges(SqlChangeReadUnitOfWork(owned.api.sessions), HASHER),
                ChangeStreamPolicy(poll_seconds=0.001),
            )
        )
    )
    async with app.router.lifespan_context(app):
        yield app


async def test_real_sse_releases_sql_before_send_and_revocation_closes_live_stream(
    identity_engine: AsyncEngine,
) -> None:
    owned = await chat(identity_engine)
    await drain(owned)
    baseline = (await head_positions(owned))[owned.recipient.id]
    await owned.send()(owned.command())
    await drain(owned)
    bodies: list[bytes] = []
    starts: list[int] = []
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
        "server": ("peerly.test", 443),
        "headers": [
            (b"cookie", f"{SESSION_COOKIE}={owned.recipient.credential.value}".encode()),
            (b"last-event-id", str(baseline).encode()),
        ],
    }

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            starts.append(message["status"])
        elif message["type"] == "http.response.body" and message.get("body"):
            bodies.append(message["body"])
            async with owned.api.sessions.begin() as session:
                # NOWAIT proves the preceding read released its account lock before I/O.
                await session.scalar(
                    select(AccountRecord)
                    .where(AccountRecord.id == owned.recipient.id)
                    .with_for_update(nowait=True)
                )
                await session.execute(
                    update(SessionRecord)
                    .where(SessionRecord.account_id == owned.recipient.id)
                    .values(revoked_at=func.clock_timestamp())
                )

    async with application(owned) as app, asyncio.timeout(5):
        await app(scope, receive, send)
    assert starts == [200]
    assert len(bodies) == 1
    frame = bodies[0].decode()
    assert frame.startswith(f"id: {baseline + 1}\nevent: resource.changed\n")
    assert str(owned.conversation_id) in frame
    assert 'resource_type":"conversation' in frame
    private_text = owned.command().content.text
    assert private_text is not None
    assert private_text not in frame
    assert str(owned.recipient.id) not in frame
    assert owned.recipient.credential.value not in frame
