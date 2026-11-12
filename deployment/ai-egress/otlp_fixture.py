"""Isolated synthetic collector; never imported or copied into gateway image."""

import json
import threading
import time
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import override

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

MAX_BODY = 1048576
COUNTS: dict[str, int] = {"traces": 0, "metrics": 0, "redirect": 0, "slow": 0}
LOCK = threading.Lock()


def protocol_kind(path: str, data: bytes) -> str | None:
    if path == "/v1/traces":
        return "traces" if ExportTraceServiceRequest.FromString(data).resource_spans else None
    if path == "/v1/metrics":
        return "metrics" if ExportMetricsServiceRequest.FromString(data).resource_metrics else None
    return None


class Collector(BaseHTTPRequestHandler):
    @override
    def log_message(self, template: str, *args: object) -> None:
        del template, args

    def respond(self, status: int, body: bytes = b"") -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path != "/fixture-counts":
            self.respond(404)
            return
        with LOCK:
            body = json.dumps(COUNTS).encode()
        self.respond(200, body)

    def do_POST(self) -> None:
        self.connection.settimeout(2)
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= length <= MAX_BODY:
                self.respond(413)
                return
            data = self.rfile.read(length)
            if len(data) != length:
                self.respond(400)
                return
            kind = protocol_kind(self.path, data)
            if kind is None:
                self.respond(400)
                return
        except (ValueError, TimeoutError):
            self.respond(400)
            return
        with LOCK:
            COUNTS[kind] += 1
        mode = self.headers.get("X-Synthetic-Mode")
        if mode == "redirect":
            with LOCK:
                COUNTS["redirect"] += 1
            self.send_response(307)
            self.send_header("Location", "http://unapproved.invalid:4318/private")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if mode == "slow":
            with LOCK:
                COUNTS["slow"] += 1
            time.sleep(3)
        self.respond(200)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 4318), Collector)  # noqa: S104 - isolated fixture namespace, no host ports.
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.1)


if __name__ == "__main__":
    main()
