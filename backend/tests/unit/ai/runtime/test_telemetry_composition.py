"""Production factory observes its real step without granting provider authority."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy.ext.asyncio import async_sessionmaker

from studymate.domain.ai.jobs import AiJob, Failure
from studymate.domain.ai.tasks import AiResult, AiTask, ClarifiedGoal
from studymate.infrastructure.ai.credentials import DedicatedCredentialCache
from studymate.infrastructure.ai.process import CodexProcessExecutor
from studymate.infrastructure.ai.queue import AiQueueSnapshot, SqlAiQueue
from studymate.infrastructure.ai.runtime import factory
from studymate.infrastructure.ai.runtime.factory import create_ai_worker_runtime
from studymate.infrastructure.ai.runtime.health import SqlRuntimeHealth
from studymate.infrastructure.ai.runtime.preflight import PinnedCli
from studymate.infrastructure.observability.origin import ExecutionOrigin
from tests.integration.media_fixture import Storage
from tests.unit.ai.runtime.test_factory import configuration
from tests.unit.ai.test_telemetry import signals as signals
from tests.unit.ai.test_worker import running_job

SignalFixture = tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader]


async def test_factory_runtime_emits_real_step_result_and_stops_sampler_before_retirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signals: SignalFixture
) -> None:
    tracer, exported, meter, reader = signals
    job = running_job()
    stop, sampling, sample_cleaned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    steps: list[str] = []

    async def verify(_self: PinnedCli) -> None:
        return None

    async def receipt(*_args: object, **_kwargs: object) -> object:
        return object()

    async def cache(_self: DedicatedCredentialCache) -> None:
        return None

    async def register(_self: SqlRuntimeHealth) -> None:
        return None

    async def heartbeat(_self: SqlRuntimeHealth, *, ready: bool = False) -> None:
        del ready

    async def revoke(_self: SqlRuntimeHealth, *, clean: bool) -> None:
        assert sample_cleaned.is_set()
        steps.append("retired" if clean else "revoked")

    async def recover(_self: SqlRuntimeHealth, queue: SqlAiQueue) -> None:
        assert queue.worker_id is not None
        steps.append("physical_cleanup")

    async def claim(_self: SqlAiQueue) -> AiJob:
        return job

    async def origin(_self: SqlAiQueue, job_id: object) -> ExecutionOrigin:
        assert job_id == job.id
        return ExecutionOrigin(job.id, job.actor_id, "a" * 32, "b" * 16)

    async def snapshot(_self: SqlAiQueue) -> AiQueueSnapshot:
        sampling.set()
        try:
            await asyncio.Event().wait()
        finally:
            sample_cleaned.set()
        raise AssertionError("Unreachable")

    async def execute(
        _self: CodexProcessExecutor, task: AiTask, _budget_seconds: float
    ) -> AiResult:
        assert task == job.task
        await sampling.wait()
        return ClarifiedGoal("Synthetic result")

    async def complete(
        _self: SqlAiQueue,
        actual: AiJob,
        result: AiResult | Failure,
        *,
        stopped: bool,
        retry_after: timedelta = timedelta(seconds=2),
    ) -> AiJob:
        assert actual == job
        assert stopped
        assert isinstance(result, ClarifiedGoal)
        del retry_after
        stop.set()
        return actual.finish(result, datetime.now(UTC))

    for target, name, replacement in [
        (PinnedCli, "verify", verify),
        (factory, "validate_runtime_receipt", receipt),
        (DedicatedCredentialCache, "validate_ready", cache),
        (SqlRuntimeHealth, "register", register),
        (SqlRuntimeHealth, "heartbeat", heartbeat),
        (SqlRuntimeHealth, "revoke", revoke),
        (SqlRuntimeHealth, "recover_current_stopped", recover),
        (SqlAiQueue, "claim", claim),
        (SqlAiQueue, "origin", origin),
        (SqlAiQueue, "complete", complete),
        (SqlAiQueue, "snapshot", snapshot),
        (CodexProcessExecutor, "execute", execute),
    ]:
        monkeypatch.setattr(target, name, replacement)
    runtime = create_ai_worker_runtime(
        async_sessionmaker(),
        Storage(b"synthetic"),
        configuration(tmp_path),
        tracer=tracer.get_tracer("synthetic"),
        meter=meter.get_meter("synthetic"),
    )
    await asyncio.wait_for(runtime.run(stop), timeout=2)
    assert steps == ["revoked", "physical_cleanup", "retired"]
    span = exported.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["ai.outcome"] == "succeeded"
    assert span.links[0].context.trace_id == int("a" * 32, 16)
    assert not span.events
    assert "Synthetic result" not in repr(span.attributes)
    data = reader.get_metrics_data()
    assert data is not None
    assert "worker.ai.attempts" in repr(data)
    assert "Synthetic result" not in repr(data)
