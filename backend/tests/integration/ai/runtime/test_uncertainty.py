"""Actual durable slot stays occupied after credential uncertainty; never lease-only recovery."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.ai.ports import AiExecutorStateUncertainError
from studymate.application.ai.worker import ExecuteNextJob
from studymate.application.idempotency import IntentKey
from studymate.domain.ai.jobs import JobState
from studymate.infrastructure.ai.runtime.supervisor import AiWorkerSupervisor, WorkerState
from tests.integration.ai.test_queue import goal, services, submission
from tests.integration.student_actor import actor
from tests.unit.ai.runtime.test_supervisor import UncertainExecutor, UncertainOnStopExecutor

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("phase", ["execution", "shutdown", "heartbeat_loss"])
async def test_credential_uncertainty_retains_actual_slot_and_prevents_second_claim(
    ai_engine: AsyncEngine,
    phase: str,
) -> None:
    owner = await actor(ai_engine)
    api = services(ai_engine)
    source = await goal(ai_engine, owner)
    first = await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    second = await api.submit(
        owner.credential, submission(source, "Different synthetic goal"), IntentKey(str(uuid4()))
    )
    executor = UncertainOnStopExecutor() if phase != "execution" else UncertainExecutor()
    supervisor = AiWorkerSupervisor(ExecuteNextJob(api.queue, executor, heartbeat_seconds=0.01))
    stop = asyncio.Event()
    operation = asyncio.create_task(supervisor.run(stop))
    if isinstance(executor, UncertainOnStopExecutor):
        await executor.started.wait()
        if phase == "shutdown":
            stop.set()
        else:
            await api.cancel(owner.credential, first.id)
    with pytest.raises(AiExecutorStateUncertainError):
        await operation
    assert supervisor.state == WorkerState.BLOCKED
    assert (await api.queue.snapshot()).occupied
    assert await api.queue.claim() is None
    assert (await api.read(owner.credential, first.id)).state == (
        JobState.CANCELLED if phase == "heartbeat_loss" else JobState.RUNNING
    )
    assert (await api.read(owner.credential, second.id)).state == JobState.QUEUED
