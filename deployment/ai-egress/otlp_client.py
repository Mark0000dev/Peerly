"""Actual locked SDK HTTP export + negative protocol controls; synthetic only."""

import concurrent.futures
import http.client
import json
import os
import socket
import sys
import time
from http import HTTPStatus

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, MetricExportResult
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

HOST = "peerly-ai-otel"
ORIGIN = "http://peerly-ai-otel:4318"
HEADERS = {"Host": "peerly-ai-otel:4318", "Content-Type": "application/x-protobuf"}
# One resource_spans entry: valid wire protobuf; native SDK positives are separate.
TRACE_BODY = b"\x0a\x00"
CHECKS: list[str] = []
MAX_FAILURE_LATENCY = 3
MEASUREMENTS: dict[str, float] = {}


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RuntimeError(code)
    CHECKS.append(code)


def request(
    method: str, path: str, *, headers: dict[str, str] | None = None, body: bytes = TRACE_BODY
) -> int:
    connection = http.client.HTTPConnection(HOST, 4318, timeout=4)
    try:
        connection.request(method, path, body, headers=HEADERS | (headers or {}))
        response = connection.getresponse()
        response.read(4096)
        return response.status
    finally:
        connection.close()


def native_exports() -> None:
    resource = Resource({"service.name": "synthetic-ai-otlp", "service.version": "fixture"})
    memory = InMemorySpanExporter()
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(memory))
    with provider.get_tracer("synthetic").start_as_current_span("synthetic-route-proof"):
        pass
    exporter: SpanExporter = OTLPSpanExporter(endpoint=ORIGIN + "/v1/traces", timeout=2)
    try:
        require(
            exporter.export(memory.get_finished_spans()) == SpanExportResult.SUCCESS,
            "native_sdk_traces",
        )
    finally:
        exporter.shutdown()
        provider.shutdown()
    reader = InMemoryMetricReader()
    meters = MeterProvider(resource=resource, metric_readers=[reader])
    meters.get_meter("synthetic").create_counter("synthetic.gateway.calls").add(1)
    data = reader.get_metrics_data()
    if data is None:
        raise RuntimeError("no_synthetic_metrics")
    metric = OTLPMetricExporter(endpoint=ORIGIN + "/v1/metrics", timeout=2)
    try:
        require(metric.export(data) == MetricExportResult.SUCCESS, "native_sdk_metrics")
    finally:
        metric.shutdown()
        meters.shutdown()


def protocol_denials() -> None:
    for index, (method, path, headers) in enumerate(
        (
            ("GET", "/v1/traces", {}),
            ("CONNECT", "other.invalid:443", {}),
            ("POST", "/v1/logs", {}),
            ("POST", "/v1/traces?target=other", {}),
            ("POST", "http://other.invalid/v1/traces", {}),
            ("POST", "/v1/%74races", {}),
            ("POST", "/fixture-counts", {}),
            ("POST", "/v1/traces", {"Host": "other.invalid"}),
            ("POST", "/v1/traces", {"Authorization": "synthetic-not-a-credential"}),
            ("POST", "/v1/traces", {"Cookie": "synthetic=marker"}),
            ("POST", "/v1/traces", {"Content-Type": "application/json"}),
            ("POST", "/v1/traces", {"Content-Encoding": "gzip"}),
            ("POST", "/v1/traces", {"Connection": "upgrade", "Upgrade": "websocket"}),
            ("POST", "/v1/traces", {"Transfer-Encoding": "chunked"}),
        )
    ):
        try:
            status = request(method, path, headers=headers)
        except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError):
            # Strict HAProxy framing rejection may close without an HTTP status.
            # Later positive redirect/slow probes + collector counts prevent a
            # stopped/broken gateway from being mistaken for a passing denial.
            CHECKS.append("denied_protocol_connection_closed")
        else:
            require(
                status >= HTTPStatus.BAD_REQUEST, f"denied_protocol_case_{index}_status_{status}"
            )
    require(
        request("POST", "/v1/traces", headers={"Content-Length": "1048577"})
        == HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        "oversized_body_header_denied",
    )
    require(
        request("POST", "/v1/traces", headers={"X-Synthetic-Mode": "redirect"})
        == HTTPStatus.BAD_GATEWAY,
        "redirect_not_forwarded",
    )


def network_denials() -> None:
    upstream = os.environ["SYNTHETIC_COLLECTOR_IP"]
    for host, port in ((upstream, 4318), (upstream, 80), (HOST, 80), (HOST, 4317)):
        try:
            connection = socket.create_connection((host, port), timeout=0.3)
        except OSError:
            CHECKS.append("direct_or_wrong_port_denied")
        else:
            connection.close()
            raise RuntimeError("unexpected_direct_route")
    try:
        socket.getaddrinfo("example.com", 4318)
    except socket.gaierror:
        CHECKS.append("external_dns_forwarding_denied")
    else:
        raise RuntimeError("unexpected_external_dns")


def bounded_failure() -> None:
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        calls = [
            pool.submit(request, "POST", "/v1/traces", headers={"X-Synthetic-Mode": "slow"})
            for _ in range(4)
        ]
        statuses = [call.result(timeout=4) for call in calls]
    require(
        all(
            code in {HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.GATEWAY_TIMEOUT}
            for code in statuses
        ),
        "bounded_unavailable_or_queue_status",
    )
    elapsed = time.monotonic() - started
    require(elapsed < MAX_FAILURE_LATENCY, "bounded_export_queue_latency")
    MEASUREMENTS["queue_failure_seconds"] = round(elapsed, 4)


def main() -> None:
    native_exports()
    protocol_denials()
    network_denials()
    bounded_failure()
    sys.stdout.write(json.dumps({"result": "PASS", "checks": CHECKS, **MEASUREMENTS}) + "\n")


if __name__ == "__main__":
    main()
