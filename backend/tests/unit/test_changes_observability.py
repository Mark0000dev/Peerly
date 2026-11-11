import asyncio
import json
from collections.abc import Iterator

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.changes.loop import ChangeMaintenance
from studymate.infrastructure.observability.changes import ObservedChangeStep
from studymate.infrastructure.observability.logging import SafeJsonFormatter

PRIVATE = "synthetic-private-provider-connection-message"


@pytest.fixture
def providers() -> Iterator[
    tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader]
]:
    spans = InMemorySpanExporter()
    tracing = TracerProvider(shutdown_on_exit=False)
    tracing.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    try:
        yield tracing, spans, meter, reader
    finally:
        tracing.shutdown()
        meter.shutdown()


@pytest.mark.parametrize("kind", tuple(ChangeMaintenance))
@pytest.mark.parametrize("idle", [True, False])
async def test_real_count_metrics_have_fixed_dimensions_without_idle_spans(
    providers: tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader],
    caplog: pytest.LogCaptureFixture,
    kind: ChangeMaintenance,
    idle: bool,
) -> None:
    caplog.set_level("INFO", logger="studymate.changes")
    tracing, spans, meter, reader = providers

    async def step() -> int:
        return 0 if idle else 1

    value = await ObservedChangeStep(
        step, kind, tracing.get_tracer("test"), meter.get_meter("test")
    )()
    assert value == (0 if idle else 1)
    if idle:
        assert not spans.get_finished_spans()
        assert not caplog.records
    else:
        logged = [json.loads(SafeJsonFormatter().format(record)) for record in caplog.records]
        assert logged[0]["worker"] == f"change_{kind.value}"
        assert logged[0]["outcome"] == "changed"
        assert spans.get_finished_spans()[0].name == f"changes.{kind.value}"
    data = reader.get_metrics_data()
    assert data is not None
    dimensions = [
        point.attributes
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        for point in metric.data.data_points
    ]
    assert all(
        set(attributes or {}).issubset({"maintenance", "outcome"}) for attributes in dimensions
    )


@pytest.mark.parametrize("failure", ["storage", "cancelled", "unexpected", "negative", "boolean"])
async def test_failure_telemetry_never_copies_private_errors_and_preserves_exception(
    providers: tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader],
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    caplog.set_level("INFO", logger="studymate.changes")
    tracing, spans, meter, _ = providers

    async def step() -> int:
        if failure == "storage":
            raise StorageUnavailableError(PRIVATE)
        if failure == "cancelled":
            raise asyncio.CancelledError(PRIVATE)
        if failure == "unexpected":
            raise RuntimeError(PRIVATE)
        return -1 if failure == "negative" else True

    error = (
        StorageUnavailableError
        if failure == "storage"
        else asyncio.CancelledError
        if failure == "cancelled"
        else RuntimeError
    )
    with pytest.raises(error):
        await ObservedChangeStep(
            step, ChangeMaintenance.PUBLICATION, tracing.get_tracer("test"), meter.get_meter("test")
        )()
    exported = spans.get_finished_spans()
    assert len(exported) == 1
    logged = [SafeJsonFormatter().format(record) for record in caplog.records]
    assert PRIVATE not in repr(logged)
    assert PRIVATE not in repr(exported[0].attributes)
    assert not exported[0].events


async def test_telemetry_can_be_absent_without_affecting_actual_maintenance() -> None:
    async def step() -> int:
        return 1

    assert await ObservedChangeStep(step, ChangeMaintenance.RETENTION)() == 1
