"""One trusted expiry step at a time; entrypoint/resources belong to composition."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

from studymate.application.errors import StorageUnavailableError
from studymate.application.requests.expiry import MAX_EXPIRY_BATCH
from studymate.domain.requests.states import ConnectionRequest

IDLE_SECONDS = 1.0
STORAGE_OUTAGE_SECONDS = 5.0


async def _step_until_stopped(
    step: Callable[[], Awaitable[tuple[ConnectionRequest, ...]]], stop: asyncio.Event
) -> tuple[ConnectionRequest, ...] | None:
    work = asyncio.ensure_future(step())
    stopped = asyncio.create_task(stop.wait())
    consumed = False
    try:
        await asyncio.wait((work, stopped), return_when=asyncio.FIRST_COMPLETED)
        if work.done():
            consumed = True
            return await work
        consumed = True
        work.cancel()
        with suppress(asyncio.CancelledError):
            await work
        return None
    finally:
        stopped.cancel()
        with suppress(asyncio.CancelledError):
            await stopped
        if not consumed:
            work.cancel()
            with suppress(asyncio.CancelledError):
                await work


async def run_expiry_loop(
    step: Callable[[], Awaitable[tuple[ConnectionRequest, ...]]], stop: asyncio.Event
) -> None:
    """Compose actual ExpireRequests (default100); no permissions or SQL owned here."""
    while not stop.is_set():
        try:
            changed = await _step_until_stopped(step, stop)
        except StorageUnavailableError:
            delay = STORAGE_OUTAGE_SECONDS
        else:
            if changed is None:
                return
            if len(changed) > MAX_EXPIRY_BATCH:
                raise RuntimeError("Expiry worker step exceeded its bounded batch")
            delay = IDLE_SECONDS if not changed else 0.0
        if delay:
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
