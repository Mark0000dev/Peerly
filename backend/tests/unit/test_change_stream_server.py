"""Exercise real HTTP disconnect/reconnect, beyond an in-memory ASGI transport."""

import asyncio
import socket
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from logging import ERROR
from uuid import UUID

import pytest
import uvicorn
from httpx import AsyncClient
from starlette.types import ASGIApp, Receive, Scope, Send

from studymate.application.changes.reads import ReadChanges
from studymate.domain.changes import ChangeWindow
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.changes.frames import parse_change_cursor
from studymate.presentation.changes.stream import (
    ChangeStreamingResponse,
    ChangeStreamPolicy,
    change_frames,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.test_changes import OWNER, Store, published

POLICY = ChangeStreamPolicy(poll_seconds=0.01, heartbeat_seconds=0.1, send_timeout_seconds=0.05)


class CursorStore(Store):
    async def change_window(self, recipient_id: UUID, after: int | None) -> ChangeWindow:
        window = await super().change_window(recipient_id, after)
        return replace(
            window,
            changes=tuple(
                change for change in window.changes if after is None or change.sequence > after
            ),
        )


@asynccontextmanager
async def running_server(app: ASGIApp) -> AsyncIterator[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.setblocking(False)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                http="h11",
                ws="none",
                lifespan="off",
                log_config=None,
                access_log=False,
                timeout_graceful_shutdown=1,
            )
        )
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(2):
                while not server.started:
                    if task.done():
                        await task
                        raise AssertionError("HTTP server exited before startup")
                    await asyncio.sleep(0.001)
            yield f"http://127.0.0.1:{listener.getsockname()[1]}"
        finally:
            server.should_exit = True
            async with asyncio.timeout(3):
                await task
        assert not server.server_state.tasks
        assert not server.server_state.connections


@pytest.mark.parametrize("revoke", [False, True], ids=["client-disconnect", "session-revoked"])
async def test_real_http_stream_closes_and_reconnects_from_last_delivered_cursor(
    revoke: bool, caplog: pytest.LogCaptureFixture
) -> None:
    store = CursorStore()
    store.window = ChangeWindow(OWNER, 1, 0, (published(1),))
    reader = ReadChanges(store, Sha256SessionHasher())
    closed = asyncio.Event()

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        cursor = next(
            (value.decode("ascii") for key, value in scope["headers"] if key == b"last-event-id"),
            "0",
        )
        first = await reader(CREDENTIAL, parse_change_cursor(cursor))
        frames = change_frames(reader, CREDENTIAL, first, POLICY)
        try:
            await ChangeStreamingResponse(frames, POLICY)(scope, receive, send)
        finally:
            closed.set()

    async with running_server(app) as origin, AsyncClient(base_url=origin, timeout=2) as client:
        async with client.stream("GET", "/events") as response:
            assert response.status_code == HTTPStatus.OK
            assert response.headers["content-type"].startswith("text/event-stream")
            lines = response.aiter_lines()
            assert await anext(lines) == "id: 1"
            if revoke:
                store.actor = replace(
                    store.actor, session=replace(store.actor.session, revoked_at=NOW)
                )
                async with asyncio.timeout(2):
                    remaining = [line async for line in lines]
                    assert not any(line.startswith("id:") for line in remaining)
        async with asyncio.timeout(2):
            await closed.wait()
        # The transport closes without acknowledging or fabricating cursor progress.
        assert store.reads
        assert all(after in (0, 1) for _, after in store.reads)
        store.actor = replace(store.actor, session=replace(store.actor.session, revoked_at=None))
        store.window = ChangeWindow(OWNER, 2, 0, (published(2),))
        closed.clear()
        async with client.stream("GET", "/events", headers={"Last-Event-ID": "1"}) as resumed:
            assert await anext(resumed.aiter_lines()) == "id: 2"
        async with asyncio.timeout(2):
            await closed.wait()
    assert not [record for record in caplog.records if record.levelno >= ERROR]


async def test_real_socket_backpressure_bounds_send_and_leaves_server_usable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    closed = asyncio.Event()
    generated = 0
    maximum_frames = 1024
    # Reuse one synthetic frame; do not build an unbounded per-consumer queue.
    frame = b"data: " + b"x" * 65_536 + b"\n\n"

    async def frames() -> AsyncGenerator[bytes, None]:
        nonlocal generated
        try:
            for _ in range(maximum_frames):
                generated += 1
                yield frame
        finally:
            closed.set()

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["path"] == "/health":
            await send({"type": "http.response.start", "status": HTTPStatus.OK, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
            return
        await ChangeStreamingResponse(frames(), POLICY)(scope, receive, send)

    async with running_server(app) as origin, AsyncClient(base_url=origin, timeout=2) as client:
        port = int(origin.rsplit(":", 1)[1])
        reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=1024)
        try:
            writer.write(b"GET /events HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            async with asyncio.timeout(2):
                headers = await reader.readuntil(b"\r\n\r\n")
                # Intentionally stop reading the socket body until the producer is closed.
                await closed.wait()
            assert headers.startswith(b"HTTP/1.1 200")
            assert 0 < generated < maximum_frames
            assert (await client.get("/health")).text == "ok"
            async with asyncio.timeout(2):
                remaining = await reader.read()
            # A timed-out frame is not falsely reported as a completed HTTP stream.
            assert not remaining.endswith(b"0\r\n\r\n")
        finally:
            writer.close()
            await writer.wait_closed()
    errors = [record for record in caplog.records if record.levelno >= ERROR]
    # Uvicorn closes the incomplete response after the bounded ASGI send aborts.
    assert len(errors) == 1
    assert errors[0].getMessage() == "ASGI callable returned without completing response."
    assert errors[0].exc_info is None
