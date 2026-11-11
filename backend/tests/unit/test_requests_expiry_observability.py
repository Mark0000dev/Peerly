import asyncio
import json
from collections.abc import Iterator
from dataclasses import replace

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from studymate.application.errors import StorageUnavailableError
from studymate.application.requests.expiry import MAX_EXPIRY_BATCH
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.states import ConnectionRequest
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.infrastructure.observability.requests import ObservedRequestExpiry
from tests.unit.requests.test_states import request

PRIVATE = "synthetic-private-note-provider-failure"


@pytest.fixture
def provider() -> Iterator[
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


@pytest.mark.parametrize("idle", [False, True])
async def test_expiry_reports_fixed_dimensions_and_real_ids_without_idle_spans_or_private_content(
    provider: tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader],
    idle: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.requests")
    tracing, spans, meter, reader = provider
    source = replace(request(), message=RequestText(PRIVATE, PRIVATE))
    value = source.effective(source.expires_at)

    async def step() -> tuple[ConnectionRequest, ...]:
        return () if idle else (value,)

    result = await ObservedRequestExpiry(
        step, tracing.get_tracer("test"), meter.get_meter("test")
    )()
    assert result == (() if idle else (value,))
    exported = spans.get_finished_spans()
    if idle:
        assert not exported
        assert not caplog.records
    else:
        assert exported[0].attributes is not None
        assert exported[0].attributes["connection.request.ids"] == (str(value.id),)
        assert exported[0].attributes["request.expiry.outcome"] == "changed"
        logged = [json.loads(SafeJsonFormatter().format(record)) for record in caplog.records]
        assert logged[0]["worker"] == "request_expiry"
        assert logged[0]["outcome"] == "changed"
        assert PRIVATE not in repr(exported[0].attributes)
        assert PRIVATE not in repr(logged)
    metrics = reader.get_metrics_data()
    assert metrics is not None
    dimensions = [
        point.attributes
        for resource in metrics.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        for point in metric.data.data_points
    ]
    assert all(set(attributes or {}).issubset({"outcome", "state"}) for attributes in dimensions)
    assert PRIVATE not in repr(metrics)


@pytest.mark.parametrize("failure", ["storage", "cancelled", "unexpected", "oversized"])
async def test_expiry_failures_end_safe_spans_and_preserve_original_exception(
    provider: tuple[TracerProvider, InMemorySpanExporter, MeterProvider, InMemoryMetricReader],
    failure: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.requests")
    tracing, spans, meter, _ = provider

    async def step() -> tuple[ConnectionRequest, ...]:
        if failure == "storage":
            raise StorageUnavailableError(PRIVATE)
        if failure == "cancelled":
            raise asyncio.CancelledError(PRIVATE)
        if failure == "unexpected":
            raise RuntimeError(PRIVATE)
        return (request(),) * (MAX_EXPIRY_BATCH + 1)

    expected = (
        StorageUnavailableError
        if failure == "storage"
        else asyncio.CancelledError
        if failure == "cancelled"
        else RuntimeError
    )
    with pytest.raises(expected):
        await ObservedRequestExpiry(step, tracing.get_tracer("test"), meter.get_meter("test"))()
    exported = spans.get_finished_spans()
    assert exported[0].status.status_code == StatusCode.ERROR
    assert PRIVATE not in repr(exported[0].attributes)
    assert all(PRIVATE not in SafeJsonFormatter().format(record) for record in caplog.records)


async def test_expiry_observer_without_sdk_keeps_domain_result() -> None:
    async def step() -> tuple[ConnectionRequest, ...]:
        return ()

    assert await ObservedRequestExpiry(step)() == ()
