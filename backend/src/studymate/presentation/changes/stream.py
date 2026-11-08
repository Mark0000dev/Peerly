"""Bounded SSE delivery with short, reauthorized reads and no SQL across sends."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from math import isfinite

from starlette.responses import StreamingResponse
from starlette.types import Message, Send

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


async def change_frames(
    reader: ReadChanges,
    credential: SessionCredential,
    first: ChangePage,
    policy: ChangeStreamPolicy,
) -> AsyncGenerator[bytes, None]:
    page = first
    cursor = first.after_sequence
    loop = asyncio.get_running_loop()
    heartbeat_due = loop.time() + policy.heartbeat_seconds
    reauthorize_at = loop.time() + policy.poll_seconds
    while True:
        reauthorize_now = False
        if page.reset_required:
            yield reset_frame(page.after_sequence)
            cursor = page.after_sequence
        else:
            for change in page.changes:
                yield change_frame(change)
                # Resume only after the previous frame's send completed, never before it.
                cursor = change.sequence
                if loop.time() >= reauthorize_at:
                    reauthorize_now = True
                    break
        if not page.has_more and not reauthorize_now:
            if loop.time() >= heartbeat_due:
                yield HEARTBEAT_FRAME
                heartbeat_due = loop.time() + policy.heartbeat_seconds
            await asyncio.sleep(policy.poll_seconds)
        try:
            # The use case has committed/closed its transaction before yielding a frame.
            page = await reader(credential, cursor)
            reauthorize_at = loop.time() + policy.poll_seconds
        except (UnauthenticatedError, StudentActionDeniedError, StorageUnavailableError):
            # Headers are committed: close, don't emit private errors or fake cursor progress.
            return


class SlowChangeConsumerError(Exception):
    pass


class ChangeStreamingResponse(StreamingResponse):
    """A stalled consumer cannot retain an unbounded live ASGI send operation."""

    def __init__(self, frames: AsyncGenerator[bytes, None], policy: ChangeStreamPolicy) -> None:
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

    async def stream_response(self, send: Send) -> None:
        async def bounded_send(message: Message) -> None:
            try:
                async with asyncio.timeout(self._send_timeout_seconds):
                    await send(message)
            except TimeoutError:
                raise SlowChangeConsumerError from None

        try:
            await super().stream_response(bounded_send)
        except SlowChangeConsumerError:
            return
        finally:
            await self._frames.aclose()
