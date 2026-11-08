import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from studymate.application.ai.policy import retry_delay
from studymate.application.ai.ports import AiExecutor, AiExecutorError
from studymate.domain.ai.jobs import AiJob, Failure
from studymate.domain.ai.tasks import AiResult

MAX_HEARTBEAT_SECONDS = 10


class AiWorkerQueue(Protocol):
    async def claim(self) -> AiJob | None: ...

    async def heartbeat(self, job: AiJob) -> bool: ...

    async def complete(
        self,
        job: AiJob,
        result: AiResult | Failure,
        *,
        stopped: bool,
        retry_after: timedelta = timedelta(seconds=2),
    ) -> AiJob: ...


@dataclass(frozen=True, slots=True)
class ExecuteNextJob:
    queue: AiWorkerQueue
    executor: AiExecutor
    heartbeat_seconds: float = 10

    def __post_init__(self) -> None:
        if not 0 < self.heartbeat_seconds <= MAX_HEARTBEAT_SECONDS:
            raise ValueError("Heartbeat must be positive and at most ten seconds")

    async def __call__(self) -> bool:
        job = await self.queue.claim()
        if job is None:
            return False
        seconds = min(60.0, (job.deadline - datetime.now(UTC)).total_seconds())
        if seconds <= 0:
            await self.queue.complete(job, Failure.TIMEOUT, stopped=True)
            return True
        task = asyncio.create_task(self.executor.execute(job.task, seconds))
        try:
            while not task.done():
                done, _ = await asyncio.wait((task,), timeout=self.heartbeat_seconds)
                if not done and not await self.queue.heartbeat(job):
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                    await self.queue.complete(job, Failure.EXECUTOR_LOST, stopped=True)
                    return True
            try:
                result = await task
            except AiExecutorError as error:
                await self.queue.complete(
                    job, error.failure, stopped=True, retry_after=retry_delay(job, error)
                )
            else:
                await self.queue.complete(job, result, stopped=True)
            return True
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
