"""Stop-aware bounded transport maintenance, independent of API connection pools."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from enum import StrEnum

from studymate.application.changes.publication import PUBLICATION_BATCH_SIZE
from studymate.application.changes.retention import (
    RETENTION_PREFIX_LIMIT,
    RETENTION_RECIPIENT_BATCH,
)
from studymate.application.errors import StorageUnavailableError

PUBLICATION_IDLE_SECONDS = 1.0
RETENTION_IDLE_SECONDS = 60.0
STORAGE_OUTAGE_SECONDS = 5.0


class ChangeMaintenance(StrEnum):
    PUBLICATION = "publication"
    RETENTION = "retention"


async def _step_until_stopped(
    step: Callable[[], Awaitable[int]], stop: asyncio.Event
) -> int | None:
    work = asyncio.ensure_future(step())
    stopped = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait((work, stopped), return_when=asyncio.FIRST_COMPLETED)
        if work.done():
            return await work
        return None
    finally:
        for task in (stopped, work):
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def run_change_loop(
    step: Callable[[], Awaitable[int]], stop: asyncio.Event, kind: ChangeMaintenance
) -> None:
    """Only actual PublishChanges/PruneChanges are composed by the root, never student input."""
    maximum = (
        PUBLICATION_BATCH_SIZE
        if kind == ChangeMaintenance.PUBLICATION
        else RETENTION_RECIPIENT_BATCH * RETENTION_PREFIX_LIMIT
    )
    idle = (
        PUBLICATION_IDLE_SECONDS
        if kind == ChangeMaintenance.PUBLICATION
        else RETENTION_IDLE_SECONDS
    )
    while not stop.is_set():
        try:
            changed = await _step_until_stopped(step, stop)
        except StorageUnavailableError:
            delay = STORAGE_OUTAGE_SECONDS
        else:
            if changed is None:
                return
            if isinstance(changed, bool) or not 0 <= changed <= maximum:
                raise RuntimeError("Transport maintenance exceeded its actual bounded batch")
            delay = idle if changed == 0 else 0.0
        if delay:
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)
