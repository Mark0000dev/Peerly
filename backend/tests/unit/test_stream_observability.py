"""Actual ASGI send completion, not generator iteration, defines delivery metrics."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime

import pytest
from opentelemetry.metrics import CallbackOptions
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from starlette.types import Message

from studymate.application.changes.observations import StreamEnd, StreamFrame, StreamSend
from studymate.infrastructure.observability.streams import StreamSignals
from studymate.presentation.changes.stream import (
    ChangeStreamingResponse,
    ChangeStreamPolicy,
    ChangeStreamState,
)


@dataclass
class Observation:
    active: int = 0
    ends: list[StreamEnd] = field(default_factory=list)
    frames: list[StreamFrame] = field(default_factory=list)
    sends: list[StreamSend] = field(default_factory=list)

    def opened(self) -> None:
        self.active += 1

    def closed(self, reason: StreamEnd) -> None:
        self.active -= 1
        self.ends.append(reason)

    def frame(self, kind: StreamFrame, published_at: datetime | None = None) -> None:
        del published_at
        self.frames.append(kind)

    def sent(self, seconds: float, *, outcome: StreamSend) -> None:
        assert seconds >= 0
        self.sends.append(outcome)


@pytest.mark.parametrize("mode", ["success", "timeout", "cancelled", "error"])
async def test_completed_sends_and_precise_close_outcomes_preserve_cleanup(mode: str) -> None:
    observation = Observation()
    state = ChangeStreamState(observation)
    closed = asyncio.Event()
    entered = asyncio.Event()
    never = asyncio.Event()

    async def frames() -> AsyncGenerator[bytes, None]:
        try:
            state.pending = (StreamFrame.RESET, None)
            yield b"private synthetic frame"
        finally:
            closed.set()

    async def send(message: Message) -> None:
        if message["type"] != "http.response.body" or not message.get("body"):
            return
        assert not observation.frames
        entered.set()
        if mode in {"timeout", "cancelled"}:
            await never.wait()
        if mode == "error":
            raise RuntimeError("private synthetic send failure")

    response = ChangeStreamingResponse(
        frames(), ChangeStreamPolicy(send_timeout_seconds=0.05), state
    )
    task = asyncio.create_task(response.stream_response(send))
    async with asyncio.timeout(2):
        await entered.wait()
        if mode == "cancelled":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif mode == "error":
            with pytest.raises(RuntimeError, match="private synthetic send failure"):
                await task
        else:
            await task
    assert closed.is_set()
    assert observation.active == 0
    assert observation.frames == ([StreamFrame.RESET] if mode == "success" else [])
    assert observation.sends == [StreamSend(mode)]
    assert observation.ends == [
        {
            "success": StreamEnd.COMPLETE,
            "timeout": StreamEnd.BACKPRESSURE,
            "cancelled": StreamEnd.CANCELLED,
            "error": StreamEnd.ERROR,
        }[mode]
    ]


def test_sdk_stream_callbacks_are_cached_bounded_and_disabled_after_lifetime() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    try:
        signals = StreamSignals(provider.get_meter("test"))
        stream = signals.stream()
        stream.opened()
        assert tuple(point.value for point in signals.connections(CallbackOptions())) == (1,)
        stream.frame(StreamFrame.RESET)
        stream.closed(StreamEnd.COMPLETE)
        stream.closed(StreamEnd.COMPLETE)
        assert signals.active == 0
        assert "private" not in repr(reader.get_metrics_data())
        signals.close()
        assert not signals.connections(CallbackOptions())
    finally:
        provider.shutdown()


async def test_reader_revocation_closes_observation_without_advancing_cursor() -> None:
    from dataclasses import replace

    from studymate.application.changes.reads import ReadChanges
    from studymate.infrastructure.security.session_digest import Sha256SessionHasher
    from studymate.presentation.changes.stream import change_frames
    from tests.unit.identity_store import CREDENTIAL, NOW
    from tests.unit.test_changes import Store

    store = Store()
    reader = ReadChanges(store, Sha256SessionHasher())
    first = await reader(CREDENTIAL, None)
    observation = Observation()
    state = ChangeStreamState(observation)
    policy = ChangeStreamPolicy(poll_seconds=0.001)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and message.get("body"):
            store.actor = replace(store.actor, session=replace(store.actor.session, revoked_at=NOW))

    async with asyncio.timeout(2):
        await ChangeStreamingResponse(
            change_frames(reader, CREDENTIAL, first, policy, state), policy, state
        ).stream_response(send)
    assert observation.frames == [StreamFrame.RESET]
    assert observation.ends == [StreamEnd.UNAUTHENTICATED]
    assert observation.active == 0
