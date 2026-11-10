import asyncio

import pytest

from studymate.application.ai.ports import AiExecutorStateUncertainError
from studymate.application.ai.worker import ExecuteNextJob
from studymate.domain.ai.tasks import AiResult, AiTask
from studymate.infrastructure.ai.process import CredentialStateUncertainError
from studymate.infrastructure.ai.runtime.supervisor import AiWorkerSupervisor, WorkerState
from tests.unit.ai.test_worker import Executor, Queue


class UncertainExecutor:
    async def execute(self, task: AiTask, budget_seconds: float) -> AiResult:
        assert budget_seconds > 0
        assert task is not None
        raise CredentialStateUncertainError


async def test_uncertain_credential_never_completes_releases_or_restarts() -> None:
    queue = Queue()
    supervisor = AiWorkerSupervisor(ExecuteNextJob(queue, UncertainExecutor()))
    with pytest.raises(AiExecutorStateUncertainError):
        await supervisor.run(asyncio.Event())
    assert queue.completed == []
    assert supervisor.state == WorkerState.BLOCKED
    with pytest.raises(RuntimeError, match="external recovery"):
        await supervisor.run(asyncio.Event())
    assert queue.completed == []


async def test_idle_stop_does_not_start_execution_or_wait_full_poll() -> None:
    queue, executor = Queue(job=None), Executor()
    supervisor = AiWorkerSupervisor(ExecuteNextJob(queue, executor))
    stop = asyncio.Event()
    operation = asyncio.create_task(supervisor.run(stop))
    await asyncio.sleep(0)
    stop.set()
    await asyncio.wait_for(operation, timeout=1)
    assert supervisor.state == WorkerState.STOPPED
    assert not executor.started.is_set()


async def test_graceful_stop_waits_for_executor_cleanup_and_keeps_recovery_slot() -> None:
    queue, executor = Queue(), Executor(pause=True)
    supervisor = AiWorkerSupervisor(ExecuteNextJob(queue, executor))
    stop = asyncio.Event()
    operation = asyncio.create_task(supervisor.run(stop))
    await executor.started.wait()
    with pytest.raises(RuntimeError, match="already active"):
        await supervisor.run(stop)
    stop.set()
    await operation
    assert executor.stopped.is_set()
    assert supervisor.state == WorkerState.STOPPED
    assert queue.completed == []


@pytest.mark.parametrize("seconds", [0, -1, 6])
def test_poll_bounds(seconds: float) -> None:
    with pytest.raises(ValueError, match="poll"):
        AiWorkerSupervisor(ExecuteNextJob(Queue(), Executor()), poll_seconds=seconds)


async def test_external_cancellation_cleans_executor_and_blocks_implicit_restart() -> None:
    queue, executor = Queue(), Executor(pause=True)
    supervisor = AiWorkerSupervisor(ExecuteNextJob(queue, executor))
    operation = asyncio.create_task(supervisor.run(asyncio.Event()))
    await executor.started.wait()
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert executor.stopped.is_set()
    assert supervisor.state == WorkerState.BLOCKED
    assert queue.completed == []


class UncertainOnStopExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute(self, task: AiTask, budget_seconds: float) -> AiResult:
        assert task is not None
        assert budget_seconds > 0
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            raise CredentialStateUncertainError
        raise AssertionError("Unreachable executor completion")


@pytest.mark.parametrize("phase", ["shutdown", "heartbeat_loss"])
async def test_uncertainty_during_shutdown_or_heartbeat_loss_blocks_without_complete(
    phase: str,
) -> None:
    queue = Queue(heartbeat_result=phase != "heartbeat_loss")
    executor = UncertainOnStopExecutor()
    supervisor = AiWorkerSupervisor(ExecuteNextJob(queue, executor, heartbeat_seconds=0.01))
    stop = asyncio.Event()
    operation = asyncio.create_task(supervisor.run(stop))
    await executor.started.wait()
    if phase == "shutdown":
        stop.set()
    with pytest.raises(CredentialStateUncertainError):
        await operation
    assert supervisor.state == WorkerState.BLOCKED
    assert queue.completed == []
