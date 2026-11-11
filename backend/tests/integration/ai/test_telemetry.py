import asyncio
from uuid import uuid4

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.ai.ports import AiUnavailableError
from studymate.application.ai.worker import ExecuteNextJob
from studymate.application.idempotency import IntentKey
from studymate.application.ports.http_tracing import HttpExecution
from studymate.domain.ai.jobs import Failure
from studymate.infrastructure.ai.telemetry import (
    AiAdmissionSignals,
    AiQueueSignals,
    ObservedAiQueue,
    ObservedAiStep,
    ObservedStudentSubmission,
)
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from tests.integration.ai.test_queue import goal, services, submission
from tests.integration.ai.test_saturation import SlowExecutor
from tests.integration.student_actor import actor
from tests.unit.ai.test_telemetry import signals as signals
from tests.unit.ai.test_worker import Executor

pytestmark = pytest.mark.integration

SignalFixture = tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader]


async def test_committed_job_origin_links_worker_without_private_telemetry(
    ai_engine: AsyncEngine, signals: SignalFixture
) -> None:
    tracer, exported, meter, reader = signals
    api = services(ai_engine)
    owner = await actor(ai_engine)
    source = await goal(ai_engine, owner)
    instruments = meter.get_meter("synthetic-ai")
    observed = ObservedStudentSubmission(
        api.submit,
        AiAdmissionSignals(
            instruments.create_counter("accepted"), instruments.create_counter("rejected")
        ),
    )
    tracing = OtelHttpTracing(tracer.get_tracer("synthetic-http"))
    request_id, action_id = uuid4(), uuid4()
    key = IntentKey(str(uuid4()))
    with tracing.start(HttpExecution(request_id, action_id, "POST", None)):
        first = await observed(owner.credential, submission(source, "PRIVATE_SENTINEL"), key)
    assert (
        await observed(owner.credential, submission(source, "PRIVATE_SENTINEL"), key)
    ).id == first.id
    queue = ObservedAiQueue(api.queue)
    worker = ObservedAiStep(
        ExecuteNextJob(queue, Executor()), tracer.get_tracer("synthetic-ai"), instruments
    )
    assert await worker()
    spans = exported.get_finished_spans()
    attempt = next(span for span in spans if span.name == "ai.execute")
    assert attempt.attributes is not None
    assert attempt.attributes["origin.request.id"] == str(request_id)
    assert attempt.attributes["action.id"] == str(action_id)
    assert attempt.attributes["ai.outcome"] == "succeeded"
    assert len(attempt.links) == 1
    for span in spans:
        assert "PRIVATE_SENTINEL" not in repr(span.attributes)
        assert not span.events
    assert "PRIVATE_SENTINEL" not in repr(reader.get_metrics_data())
    assert await api.queue.origin(uuid4()) is None


async def test_queue_gauges_observe_pending_running_circuit_without_holding_inference_connection(
    ai_engine: AsyncEngine, signals: SignalFixture
) -> None:
    tracer, _, meter, _ = signals
    api = services(ai_engine)
    owner = await actor(ai_engine)
    gauges = AiQueueSignals(meter.get_meter("synthetic-ai"))
    await gauges.sample(api.queue)
    initial = gauges.latest
    assert initial.queued == 0
    assert not initial.occupied
    source = await goal(ai_engine, owner)
    await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    await gauges.sample(api.queue)
    pending = gauges.latest
    assert pending.queued == 1
    assert pending.oldest_seconds >= 0
    fake = SlowExecutor()
    worker = ObservedAiStep(
        ExecuteNextJob(ObservedAiQueue(api.queue), fake, heartbeat_seconds=0.01),
        tracer.get_tracer("synthetic-ai"),
    )
    task = asyncio.create_task(worker())
    try:
        await asyncio.wait_for(fake.started.wait(), timeout=2)
        await gauges.sample(api.queue)
        running = gauges.latest
        assert running.occupied
        assert running.queued == 0
        fake.release.set()
        assert await task
    finally:
        fake.release.set()
        if not task.done():
            await task
    await api.submit(
        owner.credential, submission(source, "Synthetic other"), IntentKey(str(uuid4()))
    )
    failure = ObservedAiStep(
        ExecuteNextJob(ObservedAiQueue(api.queue), Executor(failure=Failure.AUTH)),
        tracer.get_tracer("synthetic-ai"),
    )
    assert await failure()
    await gauges.sample(api.queue)
    paused = gauges.latest
    assert paused.circuit_open
    assert not paused.occupied
    with pytest.raises(AiUnavailableError):
        await ObservedStudentSubmission(
            api.submit,
            AiAdmissionSignals(
                meter.get_meter("synthetic-ai").create_counter("accepted"),
                meter.get_meter("synthetic-ai").create_counter("rejected"),
            ),
        )(owner.credential, submission(source), IntentKey(str(uuid4())))
