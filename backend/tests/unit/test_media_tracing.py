import asyncio
import json
from collections.abc import Iterator
from uuid import UUID

import pytest
from opentelemetry import trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from studymate.application.errors import StorageUnavailableError
from studymate.application.media.worker import PhotoProcessingStep
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.infrastructure.observability.media import (
    ObservedMediaStep,
    record_media_claim,
)
from studymate.infrastructure.observability.origin import ExecutionOrigin

PRIVATE = "private-photo-signed-url-provider-body"


@pytest.fixture
def provider() -> Iterator[tuple[TracerProvider, InMemorySpanExporter]]:
    spans = InMemorySpanExporter()
    tracing = TracerProvider(shutdown_on_exit=False)
    tracing.add_span_processor(SimpleSpanProcessor(spans))
    try:
        yield tracing, spans
    finally:
        tracing.shutdown()


@pytest.mark.parametrize("failure", ["cancelled", "storage", "unexpected"])
async def test_failed_claimed_attempt_ends_span_and_restores_sdk_context(
    provider: tuple[TracerProvider, InMemorySpanExporter],
    failure: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.media")
    tracing, exported = provider

    async def step() -> PhotoProcessingStep:
        record_media_claim(UUID(int=1), UUID(int=2), UUID(int=9), 1, None)
        assert trace.get_current_span().is_recording()
        if failure == "cancelled":
            raise asyncio.CancelledError
        if failure == "storage":
            raise StorageUnavailableError
        raise ValueError(PRIVATE)

    worker = ObservedMediaStep(step, "photo", tracing.get_tracer("test"))
    expected = (
        asyncio.CancelledError
        if failure == "cancelled"
        else StorageUnavailableError
        if failure == "storage"
        else ValueError
    )
    with pytest.raises(expected):
        await worker()
    span = exported.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR
    assert not span.events
    assert PRIVATE not in span.to_json()
    assert not trace.get_current_span().get_span_context().is_valid
    assert all(PRIVATE not in SafeJsonFormatter().format(record) for record in caplog.records)


async def test_idle_and_unclaimed_storage_failure_do_not_invent_delivery_spans(
    provider: tuple[TracerProvider, InMemorySpanExporter], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="studymate.media")
    tracing, exported = provider

    async def idle() -> PhotoProcessingStep:
        return PhotoProcessingStep.IDLE

    async def unavailable() -> PhotoProcessingStep:
        raise StorageUnavailableError

    assert (
        await ObservedMediaStep(idle, "photo", tracing.get_tracer("test"))()
        == PhotoProcessingStep.IDLE
    )
    assert not caplog.records
    with pytest.raises(StorageUnavailableError):
        await ObservedMediaStep(unavailable, "photo", tracing.get_tracer("test"))()
    assert not exported.get_finished_spans()
    assert (
        json.loads(SafeJsonFormatter().format(caplog.records[-1]))["outcome"]
        == "storage_unavailable"
    )


async def test_disabled_tracing_keeps_safe_origin_and_actor_logs_without_fabricating_trace_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.media")
    origin = ExecutionOrigin(UUID(int=3), UUID(int=4), None, None)

    async def step() -> PhotoProcessingStep:
        record_media_claim(UUID(int=1), UUID(int=2), UUID(int=9), 1, origin)
        return PhotoProcessingStep.READY

    assert await ObservedMediaStep(step, "photo")() == PhotoProcessingStep.READY
    logged = json.loads(SafeJsonFormatter().format(caplog.records[-1]))
    assert logged["account_id"] == str(UUID(int=2))
    assert logged["origin_request_id"] == str(origin.request_id)
    assert "trace_id" not in logged
    record_media_claim(UUID(int=1), UUID(int=2), UUID(int=9), 1, None)


async def test_worker_metrics_use_bounded_outcome_only() -> None:
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)

    async def step() -> PhotoProcessingStep:
        return PhotoProcessingStep.IDLE

    try:
        await ObservedMediaStep(step, "photo", meter=meter.get_meter("test"))()
        data = reader.get_metrics_data()
        assert data is not None
        names: set[str] = set()
        for resource in data.resource_metrics:
            for scope in resource.scope_metrics:
                for metric in scope.metrics:
                    names.add(metric.name)
                    assert all(
                        dict(point.attributes or {}) == {"worker": "photo", "outcome": "idle"}
                        for point in metric.data.data_points
                    )
        assert names == {"worker.media.steps", "worker.media.step.duration"}
    finally:
        meter.shutdown()
