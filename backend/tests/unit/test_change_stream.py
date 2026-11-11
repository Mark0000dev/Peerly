import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace

import pytest
from starlette.types import Message

from studymate.application.changes.reads import ReadChanges
from studymate.domain.changes import ChangeWindow
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.changes.stream import (
    ChangeStreamingResponse,
    ChangeStreamPolicy,
    change_frames,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.test_changes import OWNER, Store, published

POLICY = ChangeStreamPolicy(poll_seconds=0.001, heartbeat_seconds=0.01, send_timeout_seconds=0.005)


@pytest.mark.parametrize(
    "timings",
    [
        (0, 15, 5),
        (1, 0, 5),
        (1, 15, 0),
        (16, 15, 5),
        (1, 15, 16),
        (1, float("inf"), 5),
        (float("nan"), 15, 5),
    ],
)
def test_stream_policy_requires_finite_bounded_waits(timings: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError, match="positive bounded waits"):
        ChangeStreamPolicy(*timings)


async def test_reset_then_reauthorized_read_closes_when_session_revoked() -> None:
    store = Store()
    reader = ReadChanges(store, Sha256SessionHasher())
    first = await reader(CREDENTIAL, None)
    stream = change_frames(reader, CREDENTIAL, first, POLICY)
    assert await anext(stream) == b"id: 0\nevent: reset_required\ndata: {}\n\n"
    store.actor = replace(store.actor, session=replace(store.actor.session, revoked_at=NOW))
    async with asyncio.timeout(1):
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    assert store.reads == ((OWNER, None),)


async def test_sending_does_not_prefetch_or_advance_cursor_before_consumer_resumes() -> None:
    store = Store()
    initial = published(1)
    store.window = ChangeWindow(OWNER, 1, 0, (initial,))
    reader = ReadChanges(store, Sha256SessionHasher())
    first = await reader(CREDENTIAL, 0)
    stream = change_frames(reader, CREDENTIAL, first, POLICY)
    assert (await anext(stream)).startswith(b"id: 1\n")
    before_reads = store.reads
    assert before_reads == ((OWNER, 0),)
    following = published(2)
    store.window = ChangeWindow(OWNER, 2, 0, (following,))
    assert (await anext(stream)).startswith(b"id: 2\n")
    assert store.reads == ((OWNER, 0), (OWNER, 1))
    await stream.aclose()


async def test_blocked_send_is_cancelled_and_generator_is_closed_without_consuming_next_frame() -> (
    None
):
    closed = asyncio.Event()
    blocked = asyncio.Event()
    never = asyncio.Event()
    generated: list[int] = []

    async def frames() -> AsyncGenerator[bytes, None]:
        try:
            generated.append(1)
            yield b"id: 1\n\n"
            generated.append(2)
            yield b"id: 2\n\n"
        finally:
            closed.set()

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            blocked.set()
            await never.wait()

    response = ChangeStreamingResponse(frames(), POLICY)
    async with asyncio.timeout(1):
        await response.stream_response(send)
    assert blocked.is_set()
    assert closed.is_set()
    assert generated == [1]
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-accel-buffering"] == "no"


async def test_request_cancellation_propagates_and_closes_suspended_generator() -> None:
    closed = asyncio.Event()
    entered = asyncio.Event()
    never = asyncio.Event()

    async def frames() -> AsyncGenerator[bytes, None]:
        try:
            yield b"id: 1\n\n"
        finally:
            closed.set()

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            entered.set()
            await never.wait()

    task = asyncio.create_task(
        ChangeStreamingResponse(frames(), ChangeStreamPolicy()).stream_response(send)
    )
    async with asyncio.timeout(1):
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert closed.is_set()


async def test_slow_page_reauthorizes_before_delivering_its_remaining_old_snapshot() -> None:
    store = Store()
    store.window = ChangeWindow(OWNER, 2, 0, (published(1), published(2)))
    reader = ReadChanges(store, Sha256SessionHasher())
    first = await reader(CREDENTIAL, 0)
    stream = change_frames(reader, CREDENTIAL, first, POLICY)
    assert (await anext(stream)).startswith(b"id: 1\n")
    store.actor = replace(store.actor, session=replace(store.actor.session, revoked_at=NOW))
    await asyncio.sleep(POLICY.poll_seconds * 2)
    async with asyncio.timeout(1):
        with pytest.raises(StopAsyncIteration):
            await anext(stream)


async def test_idle_heartbeat_has_no_cursor_id_and_still_reauthorizes_between_polls() -> None:
    store = Store()
    reader = ReadChanges(store, Sha256SessionHasher())
    first = await reader(CREDENTIAL, 0)
    stream = change_frames(reader, CREDENTIAL, first, POLICY)
    async with asyncio.timeout(1):
        assert await anext(stream) == b": heartbeat\n\n"
    assert len(store.reads) > 1
    assert all(after == 0 for _, after in store.reads)
    await stream.aclose()
