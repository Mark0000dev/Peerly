"""Owned SDK providers; OTLP network I/O only runs in bounded SDK export threads."""

import asyncio
from contextlib import ExitStack
from dataclasses import dataclass
from uuid import uuid4

from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanLimits, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

from studymate.infrastructure.observability.tracing import OtelHttpTracing

EXPORT_TIMEOUT_SECONDS = 2
METRIC_EXPORT_INTERVAL_MS = 30000
METRIC_SHUTDOWN_TIMEOUT_MS = 5000
TRACE_BATCH_SIZE = 64
TRACE_EXPORT_INTERVAL_MS = 1000
METRIC_KEYS = frozenset({"http.request.method", "http.route", "http.response.status_code"})


@dataclass(frozen=True, slots=True)
class TelemetryConfiguration:
    service_name: str
    collector_origin: str
    environment: str
    release: str
    trace_queue_capacity: int


@dataclass(frozen=True, slots=True)
class TelemetryRuntime:
    tracing: OtelHttpTracing
    tracer_provider: TracerProvider
    meter_provider: MeterProvider

    async def shutdown(self) -> None:
        await asyncio.to_thread(self._shutdown)

    def _shutdown(self) -> None:
        try:
            self.meter_provider.shutdown(timeout_millis=METRIC_SHUTDOWN_TIMEOUT_MS)
        finally:
            self.tracer_provider.shutdown()


def build_telemetry(configuration: TelemetryConfiguration) -> TelemetryRuntime:
    with ExitStack() as cleanup:
        return _build_telemetry(configuration, cleanup)


def _build_telemetry(configuration: TelemetryConfiguration, cleanup: ExitStack) -> TelemetryRuntime:
    resource = Resource(
        {
            "service.name": configuration.service_name,
            "service.instance.id": str(uuid4()),
            "deployment.environment.name": configuration.environment,
            "service.version": configuration.release,
        }
    )
    tracer = TracerProvider(
        resource=resource,
        sampler=ALWAYS_ON,
        span_limits=SpanLimits(
            max_attributes=32, max_events=0, max_links=1, max_attribute_length=256
        ),
        shutdown_on_exit=False,
    )
    cleanup.callback(tracer.shutdown)
    tracer.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=configuration.collector_origin + "/v1/traces",
                timeout=EXPORT_TIMEOUT_SECONDS,
                compression=Compression.NoCompression,
            ),
            max_queue_size=configuration.trace_queue_capacity,
            max_export_batch_size=min(TRACE_BATCH_SIZE, configuration.trace_queue_capacity),
            schedule_delay_millis=TRACE_EXPORT_INTERVAL_MS,
            export_timeout_millis=EXPORT_TIMEOUT_SECONDS * 1000,
        )
    )
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=configuration.collector_origin + "/v1/metrics",
            timeout=EXPORT_TIMEOUT_SECONDS,
            compression=Compression.NoCompression,
        ),
        export_interval_millis=METRIC_EXPORT_INTERVAL_MS,
        export_timeout_millis=EXPORT_TIMEOUT_SECONDS * 1000,
    )
    cleanup.callback(reader.shutdown, timeout_millis=METRIC_SHUTDOWN_TIMEOUT_MS)
    meter = MeterProvider(
        resource=resource,
        metric_readers=[reader],
        shutdown_on_exit=False,
        views=[
            View(instrument_name="http.server.requests", attribute_keys=set(METRIC_KEYS)),
            View(
                instrument_name="http.server.request.duration",
                attribute_keys=set(METRIC_KEYS),
                aggregation=ExplicitBucketHistogramAggregation(
                    boundaries=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
                ),
            ),
        ],
    )
    runtime = TelemetryRuntime(
        OtelHttpTracing(tracer.get_tracer("studymate"), meter.get_meter("studymate")), tracer, meter
    )
    cleanup.pop_all()
    return runtime
