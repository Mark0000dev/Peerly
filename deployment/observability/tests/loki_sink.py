"""Credential-free OTLP HTTP boundary double, not a Loki compatibility emulator."""

import base64
import gzip
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from threading import Lock

CAPACITY = 64
LOCK = Lock()
ACCEPTING = False
ATTEMPTS = 0
RECORDS: list[dict[str, str]] = []


class Sink(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        # The synthetic canary deliberately contains private-looking values.
        # Never echo the received payload into diagnostic output.
        del fmt, args

    def do_GET(self) -> None:
        global ACCEPTING
        if self.path == "/accept":
            with LOCK:
                ACCEPTING = True
        with LOCK:
            body = json.dumps({"attempts": ATTEMPTS, "records": RECORDS}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        global ATTEMPTS
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 2 * 1024 * 1024:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        if self.headers.get("Content-Encoding") == "gzip":
            with gzip.GzipFile(fileobj=BytesIO(body)) as compressed:
                body = compressed.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                self.send_error(413)
                return
        with LOCK:
            ATTEMPTS += 1
            accepted = ACCEPTING and self.path == "/otlp/v1/logs"
            if accepted and len(RECORDS) < CAPACITY:
                RECORDS.append({"path": self.path, "payload": base64.b64encode(body).decode()})
        self.send_response(200 if accepted else 503)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", "0")
        self.end_headers()


if __name__ == "__main__":
    # This private Docker-network fixture is published on host loopback only.
    ThreadingHTTPServer(("0.0.0.0", 8080), Sink).serve_forever()  # noqa: S104
