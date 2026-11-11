"""Bounded SSE delivery with short, reauthorized reads and no SQL across sends."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from time import perf_counter

from starlette.responses import StreamingResponse
from starlette.types import Message, Send

from studymate.application.changes.observations import (
    StreamEnd,
    StreamFrame,
    StreamObservation,
    StreamSend,
)
from studymate.application.changes.reads import ChangePage, ReadChanges
from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import (
    SessionCredential,
    StudentActionDeniedError,
    UnauthenticatedError,
)
from studymate.presentation.changes.frames import HEARTBEAT_FRAME, change_frame, reset_frame


@dataclass(frozen=True, slots=True)
class ChangeStreamPolicy:
    poll_seconds: float = 1.0
    heartbeat_seconds: float = 15.0
    send_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not all(
            isfinite(value)
            for value in (self.poll_seconds, self.heartbeat_seconds, self.send_timeout_seconds)
        ) or not (
            0 < self.poll_seconds <= self.heartbeat_seconds
            and 0 < self.send_timeout_seconds <= self.heartbeat_seconds
        ):
            raise ValueError("Change transport timings require positive bounded waits")


@dataclass(slots=True)
class ChangeStreamState:
    observation: StreamObservation | None = None
    reason: StreamEnd = StreamEnd.COMPLETE
    pending: tuple[StreamFrame, datetime | None] | None = None

    def delivered(self) -> None:
        if self.pending is not None and self.observation is not None:
            self.observation.frame(*self.pending)
        self.pending = None


async def change_frames(
    reader: ReadChanges,
    credential: SessionCredential,
    first: ChangePage,
    policy: ChangeStreamPolicy,
    state: ChangeStreamState | None = None,
) -> AsyncGenerator[bytes, None]:
    state = state if state is not None else ChangeStreamState()
    page = first
    cursor = first.after_sequence
    loop = asyncio.get_running_loop()
    heartbeat_due = loop.time() + policy.heartbeat_seconds
    reauthorize_at = loop.time() + policy.poll_seconds
    while True:
        reauthorize_now = False
        if page.reset_required:
            state.pending = (StreamFrame.RESET, None)
            yield reset_frame(page.after_sequence)
            cursor = page.after_sequence
        else:
            for change in page.changes:
                state.pending = (StreamFrame.CHANGE, change.published_at)
                yield change_frame(change)
                # Resume only after the previous frame's send completed, never before it.
                cursor = change.sequence
                if loop.time() >= reauthorize_at:
                    reauthorize_now = True
                    break
        if not page.has_more and not reauthorize_now:
            if loop.time() >= heartbeat_due:
                state.pending = (StreamFrame.HEARTBEAT, None)
                yield HEARTBEAT_FRAME
                heartbeat_due = loop.time() + policy.heartbeat_seconds
            await asyncio.sleep(policy.poll_seconds)
        try:
            # The use case has committed/closed its transaction before yielding a frame.
            page = await reader(credential, cursor)
            reauthorize_at = loop.time() + policy.poll_seconds
        except UnauthenticatedError:
            state.reason = StreamEnd.UNAUTHENTICATED
            return
        except StudentActionDeniedError:
            state.reason = StreamEnd.DENIED
            return
        except StorageUnavailableError:
            state.reason = StreamEnd.STORAGE
            return


class SlowChangeConsumerError(Exception):
    pass


class ChangeStreamingResponse(StreamingResponse):
    """A stalled consumer cannot retain an unbounded live ASGI send operation."""

    def __init__(
        self,
        frames: AsyncGenerator[bytes, None],
        policy: ChangeStreamPolicy,
        state: ChangeStreamState | None = None,
    ) -> None:
        super().__init__(
            frames,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "private, no-store",
                "Referrer-Policy": "no-referrer",
                "X-Accel-Buffering": "no",
            },
        )
        self._send_timeout_seconds = policy.send_timeout_seconds
        self._frames = frames
        self._state = state if state is not None else ChangeStreamState()

    async def stream_response(self, send: Send) -> None:
        state = self._state
        observation = state.observation

        async def bounded_send(message: Message) -> None:
            body = message["type"] == "http.response.body" and bool(message.get("body"))
            started = perf_counter()
            outcome = StreamSend.ERROR
            try:
                async with asyncio.timeout(self._send_timeout_seconds):
                    await send(message)
                outcome = StreamSend.SUCCESS
                if body:
                    state.delivered()
            except TimeoutError:
                outcome = StreamSend.TIMEOUT
                raise SlowChangeConsumerError from None
            except asyncio.CancelledError:
                outcome = StreamSend.CANCELLED
                raise
            finally:
                if body and observation is not None:
                    observation.sent(perf_counter() - started, outcome=outcome)

        if observation is not None:
            observation.opened()
        try:
            await super().stream_response(bounded_send)
        except SlowChangeConsumerError:
            state.reason = StreamEnd.BACKPRESSURE
            return
        except asyncio.CancelledError:
            state.reason = StreamEnd.CANCELLED
            raise
        except BaseException:
            state.reason = StreamEnd.ERROR
            raise
        finally:
            try:
                await self._frames.aclose()
            finally:
                if observation is not None:
                    observation.closed(state.reason)
