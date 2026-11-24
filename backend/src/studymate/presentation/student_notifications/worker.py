"""Internal worker boundary: no unauthenticated HTTP send/recipient selector."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from studymate.application.errors import StorageUnavailableError
from studymate.application.student_notifications.worker import (
    ConsumeStudentEvents,
)


class StudentWorkerObservation(Protocol):
    """Local lifecycle facts only; no SDK, recipient or delivery payload crosses here."""

    def started(self) -> None: ...
    def activated(self) -> None: ...
    def cycle(self, storage_available: bool) -> None: ...
    def stopped(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RunStudentNotifications:
    consume: ConsumeStudentEvents
    deliver: Callable[[], Awaitable[bool]]

    observation: StudentWorkerObservation | None = None

    async def __call__(self, stop: asyncio.Event) -> None:
        if stop.is_set():
            return
        try:
            if self.observation is not None:
                self.observation.started()
            while not stop.is_set():
                try:
                    await self.consume()
                    if self.observation is not None:
                        self.observation.activated()
                    progressed = await self.deliver()
                    storage_available = True
                except StorageUnavailableError:
                    # Worker-only outage; no coupling to core requests/provider-backed success.
                    progressed = False
                    storage_available = False
                if self.observation is not None:
                    self.observation.cycle(storage_available)
                if not progressed:
                    with suppress(TimeoutError):
                        await asyncio.wait_for(stop.wait(), timeout=1)
        finally:
            if self.observation is not None:
                self.observation.stopped()
