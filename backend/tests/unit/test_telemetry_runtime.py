import asyncio
from collections.abc import Sequence
from threading import Event, get_ident
from uuid import uuid4

import pytest
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult, MetricsData
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import ValidationError

import studymate.infrastructure.observability.runtime as runtime_module
from studymate.application.ports.http_observer import HttpObservation
from studymate.application.ports.http_tracing import HttpExecution
from studymate.config import ObservabilityConfiguration
from studymate.infrastructure.observability.runtime import TelemetryConfiguration, build_telemetry

COLLECTOR = "http://controlled-collector.test:4318"
CONFIGURATION = TelemetryConfiguration("synthetic-api", COLLECTOR, "test", "synthetic", 16)


class ControlledSpans(InMemorySpanExporter):
    def __init__(self) -> None:
        super().__init__()
        self.export_threads: list[int] = []
        self.closed = False

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self.export_threads.append(get_ident())
        return super().export(spans)

    def shutdown(self) -> None:
        self.closed = True
        super().shutdown()


class ControlledMetrics(MetricExporter):
    def __init__(self) -> None:
        super().__init__()
        self.export_threads: list[int] = []
        self.records: list[MetricsData] = []
        self.closed = False

    def export(
        self, metrics_data: MetricsData, timeout_millis: float = 10000, **_kwargs: object
    ) -> MetricExportResult:
        assert timeout_millis > 0
        self.export_threads.append(get_ident())
        self.records.append(metrics_data)
        return MetricExportResult.SUCCESS

    def shutdown(self, timeout_millis: float = 30000, **_kwargs: object) -> None:
        assert timeout_millis > 0
        self.closed = True

    def force_flush(self, timeout_millis: float = 10000) -> bool:
        assert timeout_millis > 0
        return True


def controlled_exporters(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ControlledSpans, ControlledMetrics]:
    spans, metrics = ControlledSpans(), ControlledMetrics()

    def traces(**options: object) -> ControlledSpans:
        assert options["endpoint"] == COLLECTOR + "/v1/traces"
        assert options["timeout"]
        return spans

    def measurements(**options: object) -> ControlledMetrics:
        assert options["endpoint"] == COLLECTOR + "/v1/metrics"
        assert options["timeout"]
        return metrics

    monkeypatch.setattr(runtime_module, "OTLPSpanExporter", traces)
    monkeypatch.setattr(runtime_module, "OTLPMetricExporter", measurements)
    return spans, metrics


async def test_owned_providers_export_off_loop_without_changing_global_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller = get_ident()
    original = trace.get_tracer_provider()
    spans, metrics = controlled_exporters(monkeypatch)
    runtime = build_telemetry(CONFIGURATION)
    execution = HttpExecution(uuid4(), None, "GET", None)
    with runtime.tracing.start(execution) as span:
        span.completed(HttpObservation(execution.request_id, None, "GET", "/synthetic", 200, 0.1))
    await runtime.shutdown()
    assert spans.closed
    assert metrics.closed
    assert spans.export_threads
    assert metrics.export_threads
    assert all(worker != caller for worker in [*spans.export_threads, *metrics.export_threads])
    assert trace.get_tracer_provider() is original
    assert spans.get_finished_spans()
    assert metrics.records


async def test_slow_exporter_bounds_trace_backlog_without_holding_request_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, release = Event(), Event()

    class SlowSpans(ControlledSpans):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            started.set()
            assert release.wait(timeout=5)
            return super().export(spans)

    _, _metrics = controlled_exporters(monkeypatch)
    spans = SlowSpans()

    def controlled(**_options: object) -> ControlledSpans:
        return spans

    monkeypatch.setattr(runtime_module, "OTLPSpanExporter", controlled)
    runtime = build_telemetry(CONFIGURATION)

    def request() -> None:
        execution = HttpExecution(uuid4(), None, "GET", None)
        with runtime.tracing.start(execution) as span:
            span.completed(
                HttpObservation(execution.request_id, None, "GET", "/synthetic", 200, 0.1)
            )

    try:
        request()
        assert await asyncio.to_thread(started.wait, 3)
        for _ in range(CONFIGURATION.trace_queue_capacity * 4):
            request()
        assert not release.is_set()
    finally:
        release.set()
        await runtime.shutdown()
    exported = len(spans.get_finished_spans())
    assert 1 < exported <= CONFIGURATION.trace_queue_capacity + 1


def test_failed_setup_closes_already_started_trace_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans, _ = controlled_exporters(monkeypatch)

    def unavailable(**_options: object) -> ControlledMetrics:
        raise OSError("controlled setup failure")

    monkeypatch.setattr(runtime_module, "OTLPMetricExporter", unavailable)
    with pytest.raises(OSError, match="controlled setup"):
        build_telemetry(CONFIGURATION)
    assert spans.closed


@pytest.mark.parametrize(
    "origin",
    [
        "file:///private",
        "http://user:secret@collector",
        "http://collector/path",
        "http://collector?token=private",
        "http://collector:0",
        "http://collector:invalid",
        " http://collector",
    ],
)
def test_collector_configuration_rejects_credentials_and_ambiguous_origins(origin: str) -> None:
    with pytest.raises(ValidationError):
        ObservabilityConfiguration(collector_origin=origin, environment="test", release="synthetic")
