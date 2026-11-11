import asyncio
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studymate.application.ai.ports import AiExecutorError
from studymate.application.ai.worker import ExecuteNextJob
from studymate.domain.ai.jobs import AiJob, Failure, Versions
from studymate.domain.ai.tasks import AiResult, AiTask, ClarifiedGoal, ClarifyGoal, Source

MAX_EXECUTION_SECONDS = 60


class DatabaseUnavailableError(Exception):
    pass


class PhysicalStopUncertainError(Exception):
    pass


def running_job() -> AiJob:
    at = datetime.now(UTC)
    return AiJob(
        uuid4(),
        uuid4(),
        ClarifyGoal(Source(uuid4(), 1), "Synthetic"),
        b"x" * 32,
        Versions("synthetic"),
        at,
        at + timedelta(minutes=5),
        at,
    ).claim(uuid4(), 1, at)


@dataclass(slots=True)
class Queue:
    job: AiJob | None = field(default_factory=running_job)
    heartbeat_result: bool = True
    heartbeat_error: bool = False
    completed: list[AiResult | Failure] = field(default_factory=list)
    heartbeat_seen: asyncio.Event = field(default_factory=asyncio.Event)

    async def claim(self) -> AiJob | None:
        return self.job

    async def heartbeat(self, job: AiJob) -> bool:
        assert job == self.job
        self.heartbeat_seen.set()
        if self.heartbeat_error:
            raise DatabaseUnavailableError
        return self.heartbeat_result

    async def complete(
        self,
        job: AiJob,
        result: AiResult | Failure,
        *,
        stopped: bool,
        retry_after: timedelta = timedelta(seconds=2),
    ) -> AiJob:
        assert stopped
        assert retry_after >= timedelta(0)
        assert job == self.job
        self.completed.append(result)
        return job


@dataclass(slots=True)
class Executor:
    pause: bool = False
    failure: Failure | None = None
    uncertain: bool = False
    started: asyncio.Event = field(default_factory=asyncio.Event)
    stopped: asyncio.Event = field(default_factory=asyncio.Event)

    async def execute(self, task: AiTask, budget_seconds: float) -> AiResult:
        assert isinstance(task, ClarifyGoal)
        assert 0 < budget_seconds <= MAX_EXECUTION_SECONDS
        self.started.set()
        try:
            if self.pause:
                await asyncio.Event().wait()
            if self.uncertain:
                raise PhysicalStopUncertainError
            if self.failure is not None:
                raise AiExecutorError(self.failure)
            return ClarifiedGoal("Editable")
        finally:
            self.stopped.set()


async def test_idle_queue_never_starts_executor() -> None:
    queue, executor = Queue(job=None), Executor()
    assert not await ExecuteNextJob(queue, executor)()
    assert not executor.started.is_set()


async def test_worker_commits_only_after_executor_physically_stops() -> None:
    queue, executor = Queue(), Executor()
    assert await ExecuteNextJob(queue, executor)()
    assert executor.stopped.is_set()
    assert queue.completed == [ClarifiedGoal("Editable")]


@pytest.mark.parametrize(
    "failure", [Failure.AUTH, Failure.RATE_LIMIT, Failure.TIMEOUT, Failure.INVALID_OUTPUT]
)
async def test_safe_executor_failure_is_durable(failure: Failure) -> None:
    queue, executor = Queue(), Executor(failure=failure)
    assert await ExecuteNextJob(queue, executor)()
    assert queue.completed == [failure]
    assert executor.stopped.is_set()


async def test_cancelled_job_stops_process_before_releasing_slot() -> None:
    queue, executor = Queue(heartbeat_result=False), Executor(pause=True)
    assert await ExecuteNextJob(queue, executor, heartbeat_seconds=0.01)()
    assert executor.stopped.is_set()
    assert queue.completed == [Failure.EXECUTOR_LOST]


async def test_database_loss_stops_child_and_keeps_slot_occupied() -> None:
    queue, executor = Queue(heartbeat_error=True), Executor(pause=True)
    with pytest.raises(DatabaseUnavailableError):
        await ExecuteNextJob(queue, executor, heartbeat_seconds=0.01)()
    assert executor.stopped.is_set()
    assert queue.completed == []


async def test_uncertain_stop_does_not_release_or_retry() -> None:
    queue, executor = Queue(), Executor(uncertain=True)
    with pytest.raises(PhysicalStopUncertainError):
        await ExecuteNextJob(queue, executor)()
    assert queue.completed == []


async def test_supervisor_cancellation_stops_child_and_preserves_recovery_slot() -> None:
    queue, executor = Queue(), Executor(pause=True)
    operation = asyncio.create_task(ExecuteNextJob(queue, executor, heartbeat_seconds=0.01)())
    await executor.started.wait()
    await queue.heartbeat_seen.wait()
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert executor.stopped.is_set()
    assert queue.completed == []


async def test_deadline_after_claim_expires_without_process_start() -> None:
    queue, executor = Queue(), Executor()
    assert queue.job is not None
    queue.job = replace(
        queue.job,
        created_at=datetime.now(UTC) - timedelta(minutes=10),
        deadline=datetime.now(UTC) - timedelta(seconds=1),
    )
    assert await ExecuteNextJob(queue, executor)()
    assert not executor.started.is_set()
    assert queue.completed == [Failure.TIMEOUT]


@pytest.mark.parametrize("period", [0.0, -1.0, 11.0])
def test_invalid_heartbeat_period_is_rejected(period: float) -> None:
    with pytest.raises(ValueError, match="Heartbeat"):
        ExecuteNextJob(Queue(), Executor(), heartbeat_seconds=period)
