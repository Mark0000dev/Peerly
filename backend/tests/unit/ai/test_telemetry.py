import asyncio
from collections.abc import Iterator

import pytest
from opentelemetry.metrics import CallbackOptions
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from studymate.application.ai.ports import AiQuotaError, AiUnavailableError
from studymate.application.errors import StorageUnavailableError
from studymate.domain.ai.jobs import LeaseLostError
from studymate.domain.ai.tasks import AiKind
from studymate.infrastructure.ai.process import TerminationUncertainError
from studymate.infrastructure.ai.queue import AiQueueSnapshot
from studymate.infrastructure.ai.telemetry import (
    _ACTIVE,
    AiAdmissionSignals,
    AiObservation,
    AiQueueSignals,
    ObservedAiStep,
)
from studymate.infrastructure.observability.origin import ExecutionOrigin
from tests.unit.ai.test_worker import running_job


@pytest.fixture
def signals() -> Iterator[
    tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader]
]:
    exported = InMemorySpanExporter()
    tracer = TracerProvider(shutdown_on_exit=False)
    tracer.add_span_processor(SimpleSpanProcessor(exported))
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    try:
        yield tracer, exported, meter, reader
    finally:
        tracer.shutdown()
        meter.shutdown()


def test_signal_labels_and_trace_links_cannot_capture_private_payload(
    signals: tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader],
) -> None:
    tracer, exported, meter, reader = signals
    job = running_job()
    instruments = meter.get_meter("synthetic-ai")
    observation = AiObservation(
        tracer.get_tracer("synthetic-ai"),
        instruments.create_counter("attempts"),
        instruments.create_histogram("duration"),
        instruments.create_histogram("wait"),
    )
    observation.claimed(job, ExecutionOrigin(job.id, job.actor_id, "a" * 32, "b" * 16))
    observation.outcome = "succeeded"
    observation.finish(0.02)
    span = exported.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["ai.job.id"] == str(job.id)
    assert span.attributes["ai.source.version"] == 1
    assert span.links[0].context.trace_id == int("a" * 32, 16)
    assert not span.events
    assert "Synthetic" not in repr(span.attributes)
    metrics = reader.get_metrics_data()
    assert metrics is not None
    assert "Synthetic" not in repr(metrics)
    for resource in metrics.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                for point in metric.data.data_points:
                    assert point.attributes is not None
                    assert set(point.attributes) <= {"kind", "outcome"}


@pytest.mark.parametrize(
    "failure",
    [
        asyncio.CancelledError("private sentinel"),
        StorageUnavailableError("private sentinel"),
        LeaseLostError("private sentinel"),
        TerminationUncertainError("private sentinel"),
        RuntimeError("private sentinel"),
    ],
)
async def test_exception_details_never_become_telemetry(
    signals: tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader],
    failure: BaseException,
) -> None:
    tracer, exported, meter, reader = signals

    async def step() -> bool:
        observation = _ACTIVE.get()
        assert observation is not None
        observation.claimed(running_job(), None)
        raise failure

    observed = ObservedAiStep(
        step, tracer.get_tracer("synthetic-ai"), meter.get_meter("synthetic-ai")
    )
    with pytest.raises(type(failure), match="private sentinel"):
        await observed()
    assert _ACTIVE.get() is None
    for span in exported.get_finished_spans():
        assert "private sentinel" not in repr(span.attributes)
        assert not span.events
    assert "private sentinel" not in repr(reader.get_metrics_data())


async def test_idle_and_disabled_observability_are_safe() -> None:
    async def idle() -> bool:
        return False

    assert not await ObservedAiStep(idle)()
    observation = AiObservation(None, None, None, None)
    observation.claimed(running_job(), None)
    observation.finish(0.01)


EXPECTED_QUEUED = 90
EXPECTED_OLDEST = 15


def test_admission_signals_are_bounded_and_cached_gauges_do_not_access_sql(
    signals: tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader],
) -> None:
    _, _, meter, reader = signals
    instruments = meter.get_meter("synthetic-ai")
    admission = AiAdmissionSignals(
        instruments.create_counter("accepted"), instruments.create_counter("rejected")
    )
    admission.success(AiKind.CLARIFY_GOAL)
    admission.reject(AiKind.ASSESS_PHOTO, AiQuotaError())
    admission.reject(AiKind.SUGGEST_SUBJECT, AiUnavailableError())
    gauges = AiQueueSignals(instruments)
    gauges.latest = AiQueueSnapshot(
        queued=90, oldest_seconds=15.0, occupied=True, circuit_open=True
    )
    options = CallbackOptions()
    assert gauges.depth(options)[0].value == EXPECTED_QUEUED
    assert gauges.oldest(options)[0].value == EXPECTED_OLDEST
    assert gauges.occupied(options)[0].value == 1
    assert gauges.circuit(options)[0].value == 1
    metrics = reader.get_metrics_data()
    assert metrics is not None
    for resource in metrics.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                for point in metric.data.data_points:
                    assert point.attributes is not None
                    assert set(point.attributes) <= {"kind", "reason"}
