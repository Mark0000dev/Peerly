"""Unknown/stale observations never masquerade as an empty healthy SQL queue."""

import asyncio
from time import perf_counter

import pytest
from opentelemetry.metrics import CallbackOptions
from opentelemetry.sdk.metrics import MeterProvider
from sqlalchemy.ext.asyncio import async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.ai.queue import AiQueueSnapshot, SqlAiQueue
from studymate.infrastructure.ai.telemetry import AiQueueSignals

QUEUED = 7
STALE_SECONDS = 16
BOUND_SECONDS = 2


def test_callbacks_only_publish_fresh_cache_and_explicit_sample_health() -> None:
    clock = [100.0]
    meter = MeterProvider(shutdown_on_exit=False)
    try:
        signals = AiQueueSignals(meter.get_meter("synthetic"), clock=lambda: clock[0])
        options = CallbackOptions()
        for callback in (signals.depth, signals.oldest, signals.occupied, signals.circuit):
            assert callback(options) == ()
        assert signals.age(options) == ()
        assert signals.fresh(options)[0].value == 0
        with pytest.raises(LookupError, match="fresh"):
            _ = signals.latest
        signals.latest = AiQueueSnapshot(7, 12.0, True, True)
        assert signals.depth(options)[0].value == QUEUED
        assert signals.fresh(options)[0].value == 1
        clock[0] += 16
        assert signals.age(options)[0].value == STALE_SECONDS
        for callback in (signals.depth, signals.oldest, signals.occupied, signals.circuit):
            assert callback(options) == ()
        assert signals.fresh(options)[0].value == 0
        with pytest.raises(LookupError, match="fresh"):
            _ = signals.latest
        # A clock anomaly must not resurrect or mislabel a future sample.
        clock[0] = 99
        assert signals.depth(options) == ()
    finally:
        meter.shutdown()


async def test_failed_sample_keeps_original_age_then_success_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [100.0]
    meter = MeterProvider(shutdown_on_exit=False)
    queue = SqlAiQueue(async_sessionmaker())
    calls = 0

    async def snapshot(_self: SqlAiQueue) -> AiQueueSnapshot:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise StorageUnavailableError
        return AiQueueSnapshot()

    monkeypatch.setattr(SqlAiQueue, "snapshot", snapshot)
    try:
        signals = AiQueueSignals(meter.get_meter("synthetic"), clock=lambda: clock[0])
        signals.latest = AiQueueSnapshot(7, 12.0, True, True)
        clock[0] += 16
        assert not await signals.sample(queue)
        assert signals.age(CallbackOptions())[0].value == STALE_SECONDS
        assert signals.depth(CallbackOptions()) == ()
        assert await signals.sample(queue)
        assert signals.depth(CallbackOptions())[0].value == 0
        assert signals.fresh(CallbackOptions())[0].value == 1
    finally:
        meter.shutdown()


async def test_sampler_deadline_cleans_up_and_external_cancellation_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def blocked(_self: SqlAiQueue) -> AiQueueSnapshot:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
        raise AssertionError("Unreachable")

    monkeypatch.setattr(SqlAiQueue, "snapshot", blocked)
    meter = MeterProvider(shutdown_on_exit=False)
    try:
        signals = AiQueueSignals(meter.get_meter("synthetic"))
        queue = SqlAiQueue(async_sessionmaker())
        started = perf_counter()
        assert not await asyncio.wait_for(signals.sample(queue), timeout=2)
        assert perf_counter() - started < BOUND_SECONDS
        assert cleaned.is_set()
        assert signals.fresh(CallbackOptions())[0].value == 0
        entered.clear()
        cleaned.clear()
        task = asyncio.create_task(signals.sample(queue))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set()
    finally:
        meter.shutdown()


async def test_sampler_stop_does_not_wait_for_next_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()

    async def snapshot(_self: SqlAiQueue) -> AiQueueSnapshot:
        stop.set()
        return AiQueueSnapshot(1)

    monkeypatch.setattr(SqlAiQueue, "snapshot", snapshot)
    meter = MeterProvider(shutdown_on_exit=False)
    try:
        signals = AiQueueSignals(meter.get_meter("synthetic"))
        await asyncio.wait_for(signals.run(SqlAiQueue(async_sessionmaker()), stop), timeout=1)
        assert signals.latest.queued == 1
    finally:
        meter.shutdown()


async def test_unavailable_origin_does_not_strand_claimed_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime, timedelta
    from uuid import UUID

    from opentelemetry.sdk.trace import TracerProvider

    from studymate.application.ai.worker import ExecuteNextJob
    from studymate.domain.ai.jobs import AiJob, Failure
    from studymate.domain.ai.tasks import AiResult
    from studymate.infrastructure.ai.telemetry import ObservedAiQueue, ObservedAiStep
    from studymate.infrastructure.observability.origin import ExecutionOrigin
    from tests.unit.ai.test_worker import Executor, running_job

    job = running_job()
    completed = False

    async def claim(_self: SqlAiQueue) -> AiJob:
        return job

    async def origin(_self: SqlAiQueue, job_id: UUID) -> ExecutionOrigin | None:
        assert job_id == job.id
        raise StorageUnavailableError

    async def complete(
        _self: SqlAiQueue,
        actual: AiJob,
        result: AiResult | Failure,
        *,
        stopped: bool,
        retry_after: timedelta = timedelta(seconds=2),
    ) -> AiJob:
        nonlocal completed
        assert stopped
        assert not isinstance(result, Failure)
        del retry_after
        completed = True
        return actual.finish(result, datetime.now(UTC))

    monkeypatch.setattr(SqlAiQueue, "claim", claim)
    monkeypatch.setattr(SqlAiQueue, "origin", origin)
    monkeypatch.setattr(SqlAiQueue, "complete", complete)
    tracer = TracerProvider(shutdown_on_exit=False)
    try:
        step = ObservedAiStep(
            ExecuteNextJob(ObservedAiQueue(SqlAiQueue(async_sessionmaker())), Executor()),
            tracer=tracer.get_tracer("synthetic"),
        )
        assert await step()
        assert completed
    finally:
        tracer.shutdown()


async def test_bounded_batch_export_failure_cannot_replace_execution_result() -> None:
    from collections.abc import Sequence

    from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

    from studymate.infrastructure.ai.telemetry import _ACTIVE, ObservedAiStep
    from tests.unit.ai.test_worker import running_job

    class UnavailableExporter(SpanExporter):
        attempts = 0

        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            self.attempts += len(spans)
            return SpanExportResult.FAILURE

        def shutdown(self) -> None:
            return None

    exporter = UnavailableExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(
        BatchSpanProcessor(exporter, max_queue_size=16, max_export_batch_size=1)
    )

    async def step() -> bool:
        observation = _ACTIVE.get()
        assert observation is not None
        observation.claimed(running_job(), None)
        observation.outcome = "succeeded"
        return True

    try:
        assert await ObservedAiStep(step, tracer=provider.get_tracer("synthetic"))()
        assert provider.force_flush(timeout_millis=1000)
        assert exporter.attempts == 1
    finally:
        provider.shutdown()
