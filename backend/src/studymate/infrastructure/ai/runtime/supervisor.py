"""Singleton worker loop around actual queue execution. Main owns resources/entrypoint."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum

from studymate.application.ai.worker import ExecuteNextJob

MAX_POLL_SECONDS = 5


class WorkerState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    BLOCKED = "blocked"


@dataclass(slots=True)
class AiWorkerSupervisor:
    step: ExecuteNextJob
    poll_seconds: float = 1
    state: WorkerState = field(default=WorkerState.IDLE, init=False)
    _active: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not 0 < self.poll_seconds <= MAX_POLL_SECONDS:
            raise ValueError("Worker poll must be positive and at most five seconds")

    async def run(self, stop: asyncio.Event) -> None:
        if self.state == WorkerState.BLOCKED:
            raise RuntimeError("Blocked runtime requires explicit external recovery")
        if self._active:
            raise RuntimeError("Worker supervisor already active")
        self._active = True
        self.state = WorkerState.RUNNING
        stopping = asyncio.create_task(stop.wait())
        try:
            while not stop.is_set():
                execution = asyncio.create_task(self.step())
                try:
                    done, _ = await asyncio.wait(
                        (execution, stopping), return_when=asyncio.FIRST_COMPLETED
                    )
                    if stopping in done and not execution.done():
                        self.state = WorkerState.STOPPING
                        execution.cancel()
                        with suppress(asyncio.CancelledError):
                            await execution
                        break
                    worked = await execution
                finally:
                    if not execution.done():
                        execution.cancel()
                        with suppress(asyncio.CancelledError):
                            await execution
                if not worked:
                    with suppress(TimeoutError):
                        await asyncio.wait_for(asyncio.shield(stopping), self.poll_seconds)
            self.state = WorkerState.STOPPED
        except BaseException:
            # Never auto-recover/reclaim SQL slot after executor/credential uncertainty.
            self.state = WorkerState.BLOCKED
            raise
        finally:
            stopping.cancel()
            await asyncio.gather(stopping, return_exceptions=True)
            self._active = False
