from http import HTTPStatus
from threading import get_ident

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import SecretStr
from sqlalchemy.engine import make_url

import studymate.bootstrap as bootstrap_module
from studymate.bootstrap import create_app
from studymate.config import ObservabilityConfiguration, Settings
from studymate.infrastructure.observability.runtime import TelemetryConfiguration, TelemetryRuntime
from studymate.infrastructure.observability.tracing import OtelHttpTracing

pytestmark = pytest.mark.integration


async def test_application_lifespan_and_postgresql_readiness(database_url: str) -> None:
    app = create_app(Settings(database_url=SecretStr(database_url)))
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        health = await client.get("/api/health")
        ready = await client.get("/api/ready")
    assert health.status_code == HTTPStatus.OK
    assert ready.status_code == HTTPStatus.OK
    assert ready.json() == {"status": "ok"}


async def test_unreachable_database_does_not_break_liveness(
    database_url: str,
    unused_tcp_port: int,
) -> None:
    unreachable = make_url(database_url).set(host="127.0.0.1", port=unused_tcp_port)
    app = create_app(
        Settings(database_url=SecretStr(unreachable.render_as_string(hide_password=False))),
    )
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        assert (await client.get("/api/health")).status_code == HTTPStatus.OK
        assert (await client.get("/api/ready")).status_code == HTTPStatus.SERVICE_UNAVAILABLE


async def test_explicit_telemetry_is_owned_by_real_application_lifespan(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    caller = get_ident()
    closed: list[str] = []
    exported = InMemorySpanExporter()
    tracer = TracerProvider(shutdown_on_exit=False)
    tracer.add_span_processor(SimpleSpanProcessor(exported))
    meter = MeterProvider(metric_readers=[InMemoryMetricReader()], shutdown_on_exit=False)
    runtime = TelemetryRuntime(
        OtelHttpTracing(tracer.get_tracer("test"), meter.get_meter("test")), tracer, meter
    )
    stop_trace, stop_metrics = tracer.shutdown, meter.shutdown

    def trace_shutdown() -> None:
        assert get_ident() != caller
        closed.append("traces")
        stop_trace()

    def metric_shutdown(timeout_millis: float = 30000) -> None:
        assert get_ident() != caller
        closed.append("metrics")
        stop_metrics(timeout_millis=timeout_millis)

    def controlled(configuration: TelemetryConfiguration) -> TelemetryRuntime:
        assert configuration.collector_origin == "http://controlled-collector.test"
        assert configuration.service_name == "studymate-api"
        return runtime

    monkeypatch.setattr(tracer, "shutdown", trace_shutdown)
    monkeypatch.setattr(meter, "shutdown", metric_shutdown)
    monkeypatch.setattr(bootstrap_module, "build_telemetry", controlled)
    app = create_app(
        Settings(
            _env_file=None,
            database_url=SecretStr(database_url),
            observability=ObservabilityConfiguration(
                collector_origin="http://controlled-collector.test",
                environment="test",
                release="synthetic",
            ),
        )
    )
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/api/ready")
        assert response.status_code == HTTPStatus.OK
        assert response.headers["x-request-id"]
    assert closed == ["metrics", "traces"]
    _assert_readiness_trace(exported.get_finished_spans(), response.headers["x-request-id"])


def _assert_readiness_trace(spans: tuple[ReadableSpan, ...], request_id: str) -> None:
    expected_names = {"db.query", "GET /api/ready"}
    assert len(spans) == len(expected_names)
    assert {span.name for span in spans} == expected_names
    by_name = {span.name: span for span in spans}
    database_span, request_span = by_name["db.query"], by_name["GET /api/ready"]
    assert request_span.kind is SpanKind.SERVER
    assert database_span.kind is SpanKind.CLIENT
    assert request_span.parent is None
    assert request_span.context is not None
    assert database_span.context is not None
    assert database_span.parent is not None
    assert database_span.context.trace_id == request_span.context.trace_id
    assert database_span.parent.span_id == request_span.context.span_id
    assert database_span.parent.trace_id == request_span.context.trace_id
    assert request_span.start_time is not None
    assert request_span.end_time is not None
    assert database_span.start_time is not None
    assert database_span.end_time is not None
    assert (
        request_span.start_time
        <= database_span.start_time
        <= database_span.end_time
        <= request_span.end_time
    )
    assert dict(database_span.attributes or {}) == {
        "db.system": "postgresql",
        "db.pool.name": "core",
        "query.operation": "other",
    }
    assert dict(request_span.attributes or {}) == {
        "request.id": request_id,
        "http.request.method": "GET",
        "http.route": "/api/ready",
        "http.response.status_code": 200,
    }
    for span in spans:
        assert span.status.status_code is StatusCode.UNSET
        assert span.status.description is None
        assert not span.events
