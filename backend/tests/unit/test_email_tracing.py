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
from studymate.application.identity.email_delivery import DeliveryStep
from studymate.infrastructure.observability.email import (
    ObservedVerificationDelivery,
    record_delivery,
)
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.infrastructure.observability.origin import ExecutionOrigin

PRIVATE = "private-email-otp-provider-body"


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
    caplog.set_level("INFO", logger="studymate.email")
    tracing, exported = provider

    async def step() -> DeliveryStep:
        record_delivery(UUID(int=1), UUID(int=2), 1, None)
        assert trace.get_current_span().is_recording()
        if failure == "cancelled":
            raise asyncio.CancelledError
        if failure == "storage":
            raise StorageUnavailableError
        raise ValueError(PRIVATE)

    worker = ObservedVerificationDelivery(step, tracing.get_tracer("test"))
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
    caplog.set_level("INFO", logger="studymate.email")
    tracing, exported = provider

    async def idle() -> DeliveryStep:
        return DeliveryStep.IDLE

    async def unavailable() -> DeliveryStep:
        raise StorageUnavailableError

    assert (
        await ObservedVerificationDelivery(idle, tracing.get_tracer("test"))() == DeliveryStep.IDLE
    )
    assert not caplog.records
    with pytest.raises(StorageUnavailableError):
        await ObservedVerificationDelivery(unavailable, tracing.get_tracer("test"))()
    assert not exported.get_finished_spans()
    assert (
        json.loads(SafeJsonFormatter().format(caplog.records[-1]))["outcome"]
        == "storage_unavailable"
    )


async def test_disabled_tracing_keeps_safe_origin_and_actor_logs_without_fabricating_trace_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.email")
    origin = ExecutionOrigin(UUID(int=3), UUID(int=4), None, None)

    async def step() -> DeliveryStep:
        record_delivery(UUID(int=1), UUID(int=2), 1, origin)
        return DeliveryStep.DELIVERED

    assert await ObservedVerificationDelivery(step)() == DeliveryStep.DELIVERED
    logged = json.loads(SafeJsonFormatter().format(caplog.records[-1]))
    assert logged["account_id"] == str(UUID(int=2))
    assert logged["origin_request_id"] == str(origin.request_id)
    assert "trace_id" not in logged
    record_delivery(UUID(int=1), UUID(int=2), 1, None)


async def test_worker_metrics_use_bounded_outcome_only() -> None:
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)

    async def step() -> DeliveryStep:
        return DeliveryStep.IDLE

    try:
        await ObservedVerificationDelivery(step, meter=meter.get_meter("test"))()
        data = reader.get_metrics_data()
        assert data is not None
        names: set[str] = set()
        for resource in data.resource_metrics:
            for scope in resource.scope_metrics:
                for metric in scope.metrics:
                    names.add(metric.name)
                    assert all(
                        dict(point.attributes or {}) == {"outcome": "idle"}
                        for point in metric.data.data_points
                    )
        assert names == {"worker.email.steps", "worker.email.step.duration"}
    finally:
        meter.shutdown()


@pytest.mark.parametrize(
    ("trace_id", "span_id"),
    [
        (None, "b" * 16),
        ("a" * 32, None),
        ("0" * 32, "b" * 16),
        ("a" * 32, "0" * 16),
        ("A" * 32, "b" * 16),
        ("a" * 32, "invalid"),
    ],
)
def test_origin_never_accepts_partial_or_invalid_trace_context(
    trace_id: str | None, span_id: str | None
) -> None:
    with pytest.raises(ValueError, match="trace/span pair"):
        ExecutionOrigin(UUID(int=1), None, trace_id, span_id)
