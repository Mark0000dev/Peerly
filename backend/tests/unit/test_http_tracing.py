import json
from collections.abc import Iterator
from dataclasses import dataclass
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace import StatusCode
from starlette.responses import JSONResponse

from studymate.application.discovery.cursors import DiscoveryView
from studymate.application.ports.http_observer import HttpObservation
from studymate.application.ports.http_tracing import HttpExecution
from studymate.domain.discovery import DiscoveryMode
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.infrastructure.observability.tracing import (
    OtelHttpTracing,
    current_execution,
    record_authenticated_actor,
    record_discovery_query,
    record_peer_profile_resource,
)
from studymate.presentation.problems import problem
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.unexpected_errors import unexpected_problem

PRIVATE = "private-otp-email-message-provider-detail"
ACCOUNT = UUID(int=7)
REMOTE_TRACE = "a" * 32
REMOTE_SPAN = "b" * 16


@dataclass(frozen=True, slots=True)
class TelemetryHarness:
    tracing: OtelHttpTracing
    spans: InMemorySpanExporter
    metrics: InMemoryMetricReader


@pytest.fixture
def telemetry() -> Iterator[TelemetryHarness]:
    spans = InMemorySpanExporter()
    tracer = TracerProvider(
        resource=Resource({"service.name": "synthetic-test"}),
        sampler=ALWAYS_ON,
        shutdown_on_exit=False,
    )
    tracer.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    try:
        yield TelemetryHarness(
            OtelHttpTracing(tracer.get_tracer("test"), meter.get_meter("test")), spans, reader
        )
    finally:
        meter.shutdown()
        tracer.shutdown()


def application(harness: TelemetryHarness) -> FastAPI:
    app = FastAPI(
        telemetry={"tracing": False, "metrics": False, "logs": False, "auto_configure": False}
    )
    app.add_middleware(RequestCorrelation, observer=JsonHttpObserver(), tracing=harness.tracing)
    app.add_exception_handler(Exception, unexpected_problem)

    @app.get("/items/{item_id}")
    async def item(item_id: UUID) -> JSONResponse:
        assert item_id.int > 0
        record_authenticated_actor(ACCOUNT)
        return problem(HTTPStatus.NOT_FOUND, "item_unavailable")

    @app.get("/failure")
    async def failure() -> None:
        raise ValueError(PRIVATE)

    return app


async def test_traceparent_problem_log_and_actor_correlate_without_private_content(
    telemetry: TelemetryHarness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    action_id, item_id = uuid4(), uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=application(telemetry)), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/items/{item_id}?code={PRIVATE}",
            headers={
                "traceparent": f"00-{REMOTE_TRACE}-{REMOTE_SPAN}-01",
                "baggage": "user.email=" + PRIVATE,
                "Cookie": PRIVATE,
                "X-Action-ID": str(action_id),
            },
        )
    span = telemetry.spans.get_finished_spans()[0]
    assert span.name == "GET /items/{item_id}"
    assert span.parent is not None
    assert format(span.parent.span_id, "016x") == REMOTE_SPAN
    assert response.json()["trace_id"] == REMOTE_TRACE
    assert span.attributes is not None
    assert span.attributes["user.id"] == str(ACCOUNT)
    assert span.attributes["action.id"] == str(action_id)
    assert span.attributes["request.id"] == response.headers["x-request-id"]
    assert not span.events
    serialized = span.to_json()
    assert PRIVATE not in serialized
    assert str(item_id) not in serialized
    records = [record for record in caplog.records if record.name == "studymate.http"]
    logged = json.loads(SafeJsonFormatter().format(records[-1]))
    assert logged["trace_id"] == REMOTE_TRACE
    assert logged["account_id"] == str(ACCOUNT)
    assert logged["request_id"] == response.headers["x-request-id"]
    assert current_execution() is None


async def test_unhandled_error_has_safe_error_status_without_exception_events(
    telemetry: TelemetryHarness,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=application(telemetry), raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/failure")
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert response.json()["code"] == "internal_error"
        assert response.json()["request_id"] == response.headers["x-request-id"]
        assert PRIVATE not in response.text
    span = telemetry.spans.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR
    assert not span.events
    assert PRIVATE not in span.to_json()
    assert span.context is not None
    assert response.json()["trace_id"] == format(span.context.trace_id, "032x")
    failures = [record for record in caplog.records if record.name == "studymate.errors"]
    assert failures
    recorded = json.loads(SafeJsonFormatter().format(failures[-1]))
    assert recorded["request_id"] == response.headers["x-request-id"]
    assert PRIVATE not in json.dumps(recorded)
    assert current_execution() is None


def test_metrics_dimensions_exclude_all_actor_action_and_execution_ids(
    telemetry: TelemetryHarness,
) -> None:
    execution = HttpExecution(uuid4(), uuid4(), "POST", None)
    with telemetry.tracing.start(execution) as span:
        record_authenticated_actor(ACCOUNT)
        span.completed(
            HttpObservation(
                execution.request_id, execution.action_id, "POST", "/items/{item_id}", 200, 0.25
            )
        )
    data = telemetry.metrics.get_metrics_data()
    assert data is not None
    names: set[str] = set()
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                names.add(metric.name)
                for point in metric.data.data_points:
                    assert set(point.attributes or {}) == {
                        "http.request.method",
                        "http.route",
                        "http.response.status_code",
                    }
    assert names == {"http.server.requests", "http.server.request.duration"}


def test_disabled_trace_scope_still_correlates_actor_and_restores_outer_scope() -> None:
    tracing = OtelHttpTracing()
    execution = HttpExecution(uuid4(), None, "GET", None)
    with tracing.start(execution) as span:
        record_authenticated_actor(ACCOUNT)
        current = current_execution()
        assert current is not None
        assert current.account_id == ACCOUNT
        assert current.span_id is None
        assert span.trace_id is None
        span.completed(HttpObservation(execution.request_id, None, "GET", None, 404, 0))
    record_authenticated_actor(ACCOUNT)
    assert current_execution() is None


def test_peer_resource_trace_refs_never_become_metric_dimensions(
    telemetry: TelemetryHarness,
) -> None:
    peer, context = uuid4(), uuid4()
    execution = HttpExecution(uuid4(), None, "GET", None)
    record_peer_profile_resource(peer, 1, context)
    with telemetry.tracing.start(execution) as span:
        record_authenticated_actor(ACCOUNT)
        record_peer_profile_resource(peer, 1)
        record_peer_profile_resource(peer, 1, context)
        span.completed(
            HttpObservation(
                execution.request_id, None, "GET", "/api/v1/people/{person_id}", 200, 0.01
            )
        )
    attributes = telemetry.spans.get_finished_spans()[0].attributes
    assert attributes is not None
    assert attributes["studymate.peer.id"] == str(peer)
    assert attributes["studymate.photo.version"] == 1
    assert attributes["studymate.profile_access.id"] == str(context)
    data = telemetry.metrics.get_metrics_data()
    assert data is not None
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                for point in metric.data.data_points:
                    assert set(point.attributes or {}) == {
                        "http.request.method",
                        "http.route",
                        "http.response.status_code",
                    }
    record_peer_profile_resource(peer, 1, context)


def test_discovery_query_trace_facts_are_not_views_or_metric_dimensions(
    telemetry: TelemetryHarness,
) -> None:
    peer = uuid4()
    execution = HttpExecution(uuid4(), None, "GET", None)
    record_discovery_query(DiscoveryMode.FIND_HELP, DiscoveryView.CANDIDATES, (peer,))
    with telemetry.tracing.start(execution) as span:
        record_authenticated_actor(ACCOUNT)
        record_discovery_query(DiscoveryMode.FIND_HELP, DiscoveryView.CANDIDATES, (peer,))
        span.completed(
            HttpObservation(execution.request_id, None, "GET", "/api/v1/discovery", 200, 0.01)
        )
    attributes = telemetry.spans.get_finished_spans()[0].attributes
    assert attributes is not None
    assert attributes["studymate.discovery.query_source_ids"] == (str(peer),)
    assert attributes["studymate.discovery.mode"] == "find_help"
    assert attributes["studymate.discovery.view"] == "candidates"
    assert "last_activity_at" not in attributes
    data = telemetry.metrics.get_metrics_data()
    assert data is not None
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                for point in metric.data.data_points:
                    assert set(point.attributes or {}) == {
                        "http.request.method",
                        "http.route",
                        "http.response.status_code",
                    }
    with OtelHttpTracing().start(execution):
        record_discovery_query(DiscoveryMode.OFFER_HELP, DiscoveryView.PASSED, ())
