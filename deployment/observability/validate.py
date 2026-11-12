"""One bounded, credential-free native configuration/transport proof batch.

Only owned containers/networks are touched. This is not remote monitoring or Loki
compatibility acceptance. Requires Docker and the existing backend test venv only
for producing an actual SafeJsonFormatter sample; no application is started.
"""

import argparse
import base64
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from typing import Literal, override

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue

BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parents[1]
CANARY = "PRIVATE_CANARY_OTP_CHAT_COOKIE"
TRACE = "1234567890abcdef1234567890abcdef"
SPAN = "1234567890abcdef"
SOURCE_LOG_COUNT = 2
MAX_SAFE_STACK_FRAMES = 20


type Json = bool | int | float | str | list[Json] | dict[str, Json] | None
DOCKER = shutil.which("docker") or "/usr/bin/docker"
FORMATTER_SOURCE = """import logging,sys
from uuid import UUID
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.application.ports.http_observer import HttpObservation
rid=UUID("00000000-0000-4000-8000-000000000021")
r=logging.makeLogRecord({
    "name":"studymate.http","levelno":20,"msg":"PRIVATE_CANARY_OTP_CHAT_COOKIE",
    "event":"request_completed","request_id":rid,
    "trace_id":"1234567890abcdef1234567890abcdef",
    "observation":HttpObservation(rid,None,"GET","/api/v1/me",200,.01),
    "status":200,"duration_seconds":.01})
sys.stdout.write(SafeJsonFormatter(release="1111111111111111111111111111111111111111").format(r)+"\\n")
def source_failure(depth):
    if depth:
        return source_failure(depth-1)
    raise RuntimeError("PRIVATE_CANARY_OTP_CHAT_COOKIE")
try:
    source_failure(25)
except RuntimeError:
    error=logging.makeLogRecord({"name":"studymate.http","levelno":40,
        "msg":"PRIVATE_CANARY_OTP_CHAT_COOKIE","event":"runtime_error",
        "request_id":UUID("00000000-0000-4000-8000-000000000022"),
        "status":500,"exc_info":sys.exc_info()})
    sys.stdout.write(SafeJsonFormatter(release="3333333333333333333333333333333333333333").format(error)+"\\n")
"""


def checked_json(value: object) -> Json:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list):
        return [checked_json(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, Json] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON key must be a string")
            result[key] = checked_json(item)
        return result
    raise ValueError("Unsupported JSON value")


def parse_json(raw: str | bytes) -> Json:
    value: object = json.loads(raw)
    return checked_json(value)


def obj(value: Json) -> dict[str, Json]:
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def array(value: Json) -> list[Json]:
    if not isinstance(value, list):
        raise ValueError("Expected JSON array")
    return value


def text(value: Json) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected JSON string")
    return value


def integer(value: Json) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Expected JSON integer")
    return value


def otlp_value(value: AnyValue) -> Json:
    kind = value.WhichOneof("value")
    result: Json
    if kind == "string_value":
        result = value.string_value
    elif kind == "int_value":
        result = value.int_value
    elif kind == "double_value":
        result = value.double_value
    elif kind == "bool_value":
        result = value.bool_value
    elif kind == "array_value":
        result = [otlp_value(item) for item in value.array_value.values]
    elif kind == "kvlist_value":
        result = {item.key: otlp_value(item.value) for item in value.kvlist_value.values}
    elif kind is None:
        result = None
    else:
        raise ValueError("Unexpected byte content in safe log body")
    return result


def decoded_log_records(payload: bytes) -> list[tuple[dict[str, Json], dict[str, Json]]]:
    request = ExportLogsServiceRequest.FromString(payload)
    return [
        (
            obj(otlp_value(record.body)),
            {item.key: otlp_value(item.value) for item in resource.resource.attributes},
        )
        for resource in request.resource_logs
        for scope in resource.scope_logs
        for record in scope.log_records
    ]


def check_safe_log_metadata(
    body: dict[str, Json],
    metadata: dict[str, Json],
    wanted: dict[str, Json],
    service: str,
) -> None:
    for field in ("stack", "status", "error_type", "database_error_code", "service_release"):
        require((field in body) == (field in wanted), "Safe metadata key presence differs")
        require(body.get(field) == wanted.get(field), "Safe diagnostic metadata differs")
    require(metadata.get("service.name") == service, "Log service identity differs")
    require(
        metadata.get("service.version") == wanted.get("service_release"),
        "Log release was lost, fabricated or attributed to another service",
    )
    if "status" in body:
        integer(body["status"])
    for value in array(body.get("stack", [])):
        frame = obj(value)
        require(set(frame) == {"file", "function", "line"}, "Private frame field escaped")
        integer(frame["line"])


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run(
    args: list[str],
    output: pathlib.Path,
    name: str,
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> str:
    # All callers construct fixed Docker commands or the fixed local formatter below.
    if not args or args[0] != "docker":
        raise ValueError("Only internally constructed Docker commands are supported")
    args = [DOCKER, *args[1:]]
    result = subprocess.run(  # noqa: S603 - trusted executable and internally built argv.
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        input=input_text,
    )
    (output / (name + ".log")).write_text(result.stdout + result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed with CLI {result.returncode}; see preserved log")
    return result.stdout


def fetch(url: str, body: object | None = None) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.port is None
    ):
        raise ValueError("Proof HTTP is restricted to explicit loopback ports")
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(  # noqa: S310 - validated loopback HTTP only.
        url, data=data, headers={"Content-Type": "application/json"}
    )
    # Disable redirects and ambient proxy settings; neither may escape loopback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=3) as response:
        payload: bytes = response.read(4 * 1024 * 1024 + 1)
    if len(payload) > 4 * 1024 * 1024:
        raise ValueError("Proof response exceeds bounded capacity")
    return payload


class NoRedirect(urllib.request.HTTPRedirectHandler):
    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        raise ValueError("Proof HTTP redirects are forbidden")


def wait_for(check: Callable[[], bool], name: str, seconds: int = 60) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Bounded readiness/proof deadline exceeded: {name}")


def resource(service: str = "studymate-api") -> dict[str, object]:
    return {
        "attributes": [
            {"key": "service.name", "value": {"stringValue": service}},
            {"key": "service.version", "value": {"stringValue": "ops02-test"}},
            {"key": "deployment.environment.name", "value": {"stringValue": "test"}},
            {"key": "private.raw", "value": {"stringValue": CANARY}},
        ]
    }


WAL_BYTES = 256 * 1024 * 1024
RESOURCE_LABELS = {
    "deployment_environment_name",
    "service_name",
    "service_version",
    "job",
}


def series(payload: bytes, name: str) -> list[tuple[dict[str, str], float]]:
    result = []
    for line in payload.decode().splitlines():
        if not line.startswith(name + "{"):
            continue
        head, raw_value = line.rsplit(" ", 1)
        encoded_labels = head[len(name) + 1 : -1]
        labels = {
            match[1]: text(parse_json('"' + match[2] + '"'))
            for match in re.finditer(
                r'([A-Za-z_][A-Za-z0-9_]*)="((?:\\.|[^"\\])*)"', encoded_labels
            )
        }
        value = float(raw_value)
        require(math.isfinite(value) and value >= 0, "Nonfinite or negative observation")
        result.append((labels, value))
    require(bool(result), "Missing expected metric " + name)
    return result


METRIC_UNITS = {
    "worker.changes.steps": "{step}",
    "worker.changes.hints": "{hint}",
    "worker.changes.duration": "s",
    "db.query.duration": "s",
    "worker.external.queue.oldest_due": "s",
    "worker.external.queue.sample.age": "s",
    "worker.external.sources.oldest": "s",
    "worker.email.steps": "{step}",
    "worker.email.step.duration": "s",
    "worker.external.cycle.age": "s",
    "worker.media.steps": "{step}",
    "worker.media.step.duration": "s",
    "worker.requests.expiry.steps": "{step}",
    "worker.requests.finalized": "{request}",
    "worker.requests.expiry.duration": "s",
    "sse.delivery.lag": "s",
    "sse.send.duration": "s",
    "http.server.requests": "{request}",
    "http.server.request.duration": "s",
    "worker.ai.queue.oldest": "s",
    "worker.ai.queue.sample.age": "s",
    "worker.ai.execution.duration": "s",
    "worker.ai.wait.duration": "s",
}


def synthetic_metric(
    name: str,
    kind: Literal["gauge", "sum", "histogram"],
    now: int,
    labels: dict[str, str] | None = None,
) -> dict[str, object]:
    attributes = [
        {"key": key, "value": {"stringValue": value}}
        for key, value in {"private.raw": CANARY, **(labels or {})}.items()
    ]
    point: dict[str, object] = {"attributes": attributes, "timeUnixNano": str(now)}
    if kind == "histogram":
        point.update(
            {
                "count": "1",
                "sum": 0.01,
                "bucketCounts": ["1", "0"],
                "explicitBounds": [0.1],
            }
        )
    else:
        point["asInt"] = "1"
    data: dict[str, object] = {"dataPoints": [point]}
    if kind != "gauge":
        data["aggregationTemporality"] = 2
        point["startTimeUnixNano"] = str(now - 1000000000)
    if kind == "sum":
        data["isMonotonic"] = True
    return {"name": name, "unit": METRIC_UNITS.get(name, ""), kind: data}


class Proof:
    def __init__(self, output: pathlib.Path) -> None:
        self.output = output
        self.images = obj(parse_json((BASE / "images.json").read_text()))
        self.prefix = "peerly-ops02-" + uuid.uuid4().hex[:10]
        self.network = self.prefix + "-net"
        self.owned: list[str] = []
        self.wal_volume = self.prefix + "-wal"
        self.wal_created = False
        self.report: dict[str, object] = {
            "scope": "local synthetic native config/transport only",
            "checks": [],
            "result": "NOT COMPLETE",
            "owned_containers": self.owned,
        }
        self.started = time.monotonic()
        self.environment = dict(os.environ)
        self.environment.update(
            {
                "PEERLY_ENVIRONMENT": "test",
                "PEERLY_RELEASE": "ops02-test",
                "LOKI_OTLP_ENDPOINT": "http://sink:8080/otlp",
                "LOKI_AUTHORIZATION": "",
                "LOKI_TENANT_ID": "",
                "PEERLY_APPLICATION_NETWORK": self.network,
                "PEERLY_MONITORING_EGRESS_NETWORK": self.network,
                "PEERLY_COLLECTOR_DATA_DIR": str(self.output / "collector-data"),
                "PEERLY_TEMPO_DATA_DIR": str(self.output / "tempo-data"),
            }
        )
        self.container_environment = [
            item
            for key in [
                "PEERLY_ENVIRONMENT",
                "PEERLY_RELEASE",
                "LOKI_OTLP_ENDPOINT",
                "LOKI_AUTHORIZATION",
                "LOKI_TENANT_ID",
            ]
            for item in ["--env", key + "=" + self.environment[key]]
        ]
        self.snapshot = {
            str(p.relative_to(BASE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in BASE.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }
        (self.output / "source-manifest.json").write_text(
            json.dumps(self.snapshot, indent=2) + "\n"
        )

    def native_configuration(self, *, logs_only: bool = False) -> None:
        images = (
            ["collector", "validation_only_python"]
            if logs_only
            else ["collector", "tempo", "promtool", "validation_only_python"]
        )
        for key in images:
            run(["docker", "pull", text(self.images[key])], self.output, "pull-" + key)
        self.mount_config = ["--mount", f"type=bind,src={BASE},dst=/config,readonly"]
        self.hardened = [
            "--user",
            "10001:10001",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "128",
            "--cpus",
            "0.5" if logs_only else "1",
        ]
        run(
            [
                "docker",
                "run",
                "--rm",
                *self.hardened,
                "--memory",
                "256m",
                *self.mount_config,
                *self.container_environment,
                text(self.images["collector"]),
                "validate",
                "--config=/config/collector/collector.yaml",
            ],
            self.output,
            "collector-validate",
        )
        run(
            [
                "docker",
                "run",
                "--rm",
                *self.hardened,
                "--memory",
                "256m",
                *self.mount_config,
                *self.container_environment,
                "--env",
                "PROMETHEUS_REMOTE_WRITE_URL=http://sink:8080/write",
                "--env",
                "PROMETHEUS_AUTHORIZATION=",
                text(self.images["collector"]),
                "validate",
                "--config=/config/collector/collector.yaml",
                "--config=/config/collector/remote-write.yaml",
            ],
            self.output,
            "collector-remote-write-validate",
        )
        if logs_only:
            return
        run(
            [
                "docker",
                "run",
                "--rm",
                *self.hardened,
                "--memory",
                "512m",
                *self.mount_config,
                text(self.images["tempo"]),
                "-config.file=/config/tempo/tempo.yaml",
                "-config.verify=true",
            ],
            self.output,
            "tempo-validate",
        )
        run(
            [
                "docker",
                "compose",
                "--env-file",
                "/dev/null",
                "-f",
                str(BASE / "compose.yml"),
                "config",
                "--quiet",
            ],
            self.output,
            "compose-validate",
            env=self.environment,
        )

    def prometheus_rules(self) -> None:
        prom = [
            "docker",
            "run",
            "--rm",
            *self.hardened,
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001",  # noqa: S108 - private container tmpfs.
            "--memory",
            "256m",
            *self.mount_config,
            "--entrypoint",
            "/bin/promtool",
            text(self.images["promtool"]),
        ]
        run(
            [*prom, "check", "rules", "/config/prometheus/alerts.yml"],
            self.output,
            "promtool-rules",
        )
        run(
            [*prom, "test", "rules", "/config/tests/rules.test.yml"],
            self.output,
            "promtool-rule-behavior",
        )
        # Parse every dashboard expression with the native PromQL parser too.
        dashboard = obj(parse_json((BASE / "grafana/peerly-technical.json").read_text()))
        rules = [
            {
                "record": f"ops02_dashboard_panel_{integer(obj(panel)['id'])}_{index}",
                "expr": text(obj(target)["expr"])
                .replace("$__rate_interval", "1m")
                .replace("$environment", "test"),
            }
            for panel in array(dashboard["panels"])
            for index, target in enumerate(array(obj(panel)["targets"]))
        ]
        (self.output / "dashboard-expressions.json").write_text(
            json.dumps({"groups": [{"name": "dashboard-syntax", "rules": rules}]})
        )
        run(
            [
                "docker",
                "run",
                "--rm",
                *self.hardened,
                "--memory",
                "256m",
                "--interactive",
                "--entrypoint",
                "/bin/promtool",
                text(self.images["promtool"]),
                "check",
                "rules",
                "/dev/stdin",
            ],
            self.output,
            "dashboard-promql",
            input_text=(self.output / "dashboard-expressions.json").read_text(),
        )

    def prometheus_configuration(self) -> None:
        template = (BASE / "prometheus/prometheus.yml.template").read_text()
        replacements = {
            "STAGING_OBSERVABILITY_TLS_TARGET": "fixture.invalid:443",
            "PEERLY_ENVIRONMENT": "test",
            "MONITORING_CA_FILE": "/synthetic/ca.pem",
            "SCRAPE_READ_PASSWORD_FILE": "/synthetic/reader-password",
        }
        for key, value in replacements.items():
            template = template.replace("@@" + key + "@@", value)
        template = template.replace(
            "/etc/prometheus/peerly/alerts.yml", "/config/prometheus/alerts.yml"
        )
        (self.output / "prometheus-syntax.yml").write_text(template)
        run(
            [
                "docker",
                "run",
                "--rm",
                *self.hardened,
                "--memory",
                "256m",
                *self.mount_config,
                "--interactive",
                "--entrypoint",
                "/bin/promtool",
                text(self.images["promtool"]),
                "check",
                "config",
                "--syntax-only",
                "/dev/stdin",
            ],
            self.output,
            "prometheus-config-syntax",
            input_text=template,
        )

    def start_fixtures(self, *, logs_only: bool = False) -> None:
        run(
            [
                "docker",
                "volume",
                "create",
                "--driver",
                "local",
                "--opt",
                "type=tmpfs",
                "--opt",
                "device=tmpfs",
                "--opt",
                "o=size=256m,uid=10001,gid=10001,mode=0700,nosuid,nodev",
                self.wal_volume,
            ],
            self.output,
            "bounded-wal-volume-create",
        )
        self.wal_created = True

        def start(name: str, extra: list[str], image: str, command: list[str]) -> str:
            actual = self.prefix + "-" + name
            run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--name",
                    actual,
                    "--network",
                    self.network,
                    "--network-alias",
                    name,
                    *self.hardened,
                    *extra,
                    image,
                    *command,
                ],
                self.output,
                name + "-start",
            )
            self.owned.append(actual)
            return actual

        sink = start(
            "sink",
            ["--memory", "64m", *self.mount_config, "--publish", "127.0.0.1::8080"],
            text(self.images["validation_only_python"]),
            ["python", "-B", "/config/tests/loki_sink.py"],
        )
        tempo = ""
        if not logs_only:
            tempo = start(
                "tempo",
                [
                    "--memory",
                    "512m",
                    *self.mount_config,
                    "--mount",
                    f"type=volume,src={self.wal_volume},dst=/var/tempo,volume-nocopy",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,size=16m",  # noqa: S108 - private container tmpfs.
                    "--publish",
                    "127.0.0.1::3200",
                ],
                text(self.images["tempo"]),
                ["-target=all", "-config.file=/config/tempo/tempo.yaml"],
            )
        collector = start(
            "collector",
            [
                "--memory",
                "256m",
                *self.mount_config,
                *self.container_environment,
                "--mount",
                f"type=volume,src={self.wal_volume},dst=/var/tempo-capacity,readonly,volume-nocopy",
                "--tmpfs",
                "/var/lib/otelcol:rw,nosuid,nodev,size=128m,uid=10001,gid=10001,mode=0700",
                "--publish",
                "127.0.0.1::4318",
                "--publish",
                "127.0.0.1::8889",
                "--publish",
                "127.0.0.1::8888",
                "--publish",
                "127.0.0.1::13133",
                "--publish",
                "127.0.0.1::5514",
            ],
            text(self.images["collector"]),
            ["--config=/config/collector/collector.yaml"],
        )

        def port(name: str, container_port: int) -> int:
            data = obj(
                array(parse_json(run(["docker", "inspect", name], self.output, name + "-inspect")))[
                    0
                ]
            )
            require(obj(data["Config"])["User"] == "10001:10001", "Wrong fixture UID")
            require(obj(data["HostConfig"])["ReadonlyRootfs"] is True, "Rootfs is writable")
            ports = obj(obj(data["NetworkSettings"])["Ports"])
            binding = obj(array(ports[str(container_port) + "/tcp"])[0])
            require(binding["HostIp"] == "127.0.0.1", "Port escaped loopback")
            return int(text(binding["HostPort"]))

        self.collector = collector
        self.tempo = tempo
        self.sink_url = f"http://127.0.0.1:{port(sink, 8080)}"
        self.tempo_url = f"http://127.0.0.1:{port(tempo, 3200)}" if tempo else ""
        self.otlp_url = f"http://127.0.0.1:{port(collector, 4318)}"
        self.metrics_url = f"http://127.0.0.1:{port(collector, 8889)}"
        self.self_metrics_url = f"http://127.0.0.1:{port(collector, 8888)}"
        self.health_url = f"http://127.0.0.1:{port(collector, 13133)}"
        self.syslog_port = port(collector, 5514)
        wait_for(lambda: bool(fetch(self.health_url)), "collector health")
        if not logs_only:
            wait_for(
                lambda: fetch(self.tempo_url + "/ready").strip() == b"ready",
                "Tempo readiness",
            )

    def prove_metrics(self) -> None:
        self.now = time.time_ns()
        attributes = [
            {"key": "http.request.method", "value": {"stringValue": "GET"}},
            {"key": "http.route", "value": {"stringValue": "/api/v1/me"}},
            {"key": "http.response.status_code", "value": {"intValue": "200"}},
            {"key": "request_id", "value": {"stringValue": CANARY}},
        ]
        metrics = [
            {
                "name": "http.server.requests",
                "unit": "{request}",
                "sum": {
                    "aggregationTemporality": 2,
                    "isMonotonic": True,
                    "dataPoints": [
                        {
                            "attributes": attributes,
                            "startTimeUnixNano": str(self.now - 1000000000),
                            "timeUnixNano": str(self.now),
                            "asInt": "120",
                        }
                    ],
                },
            },
            {
                "name": "http.server.request.duration",
                "unit": "s",
                "histogram": {
                    "aggregationTemporality": 2,
                    "dataPoints": [
                        {
                            "attributes": attributes,
                            "startTimeUnixNano": str(self.now - 1000000000),
                            "timeUnixNano": str(self.now),
                            "count": "1",
                            "sum": 0.75,
                            "bucketCounts": ["0", "1", "0"],
                            "explicitBounds": [0.5, 1],
                        }
                    ],
                },
            },
            {
                "name": "not.an.application.metric",
                "gauge": {"dataPoints": [{"timeUnixNano": str(self.now), "asInt": "9"}]},
            },
        ]
        fetch(
            self.otlp_url + "/v1/metrics",
            {
                "resourceMetrics": [
                    {
                        "resource": resource(),
                        "scopeMetrics": [{"scope": {"name": "studymate"}, "metrics": metrics}],
                    }
                ]
            },
        )
        wait_for(
            lambda: b"http_server_requests_total{" in fetch(self.metrics_url + "/metrics"),
            "source metric translation",
        )
        exposition = fetch(self.metrics_url + "/metrics")
        require(
            b"http_server_request_duration_seconds_bucket{" in exposition,
            "Missing duration histogram",
        )
        require(
            b"http_server_requests_total{" in exposition,
            "Missing canonical counter suffix",
        )
        require(b"not_an_application_metric" not in exposition, "Unexpected metric escaped")
        require(CANARY.encode() not in exposition, "Private metric content escaped")
        require(b"request_id=" not in exposition, "Unbounded metric dimension escaped")
        require(b'service_name="studymate-api"' in exposition, "Missing service identity")
        (self.output / "app-metrics.prom").write_bytes(exposition)
        # Native exporter self-metrics are infrastructure, not guessed app metrics.
        (self.output / "collector-metrics.prom").write_bytes(
            fetch(self.self_metrics_url + "/metrics")
        )

    def post_metrics(self, service: str, metrics: list[dict[str, object]]) -> None:
        fetch(
            self.otlp_url + "/v1/metrics",
            {
                "resourceMetrics": [
                    {
                        "resource": resource(service),
                        "scopeMetrics": [{"scope": {"name": "studymate"}, "metrics": metrics}],
                    }
                ]
            },
        )

    def prove_ops_metrics(self) -> None:
        metrics = [
            synthetic_metric(
                "db.query.duration",
                "histogram",
                self.now,
                {"pool": "core", "operation": "select"},
            ),
            synthetic_metric("db.pool.checked_out", "gauge", self.now, {"pool": "core"}),
            synthetic_metric("db.pool.configured_size", "gauge", self.now, {"pool": "core"}),
            synthetic_metric("db.pool.checked_out", "gauge", self.now, {"pool": "private_pool"}),
            synthetic_metric(
                "db.query.duration",
                "histogram",
                self.now,
                {"operation": "private_operation"},
            ),
            synthetic_metric("sse.connections.active", "gauge", self.now),
            synthetic_metric("sse.connections.closed", "sum", self.now, {"reason": "complete"}),
            synthetic_metric("sse.frames", "sum", self.now, {"kind": "change"}),
            synthetic_metric("sse.resets", "sum", self.now),
            synthetic_metric("sse.delivery.lag", "histogram", self.now),
            synthetic_metric("sse.send.duration", "histogram", self.now, {"outcome": "success"}),
            synthetic_metric(
                "system.filesystem.usage",
                "gauge",
                self.now,
                {"mountpoint": "/private-fake", "state": "used"},
            ),
        ]
        self.post_metrics("studymate-api", metrics)
        self.post_metrics(
            "studymate-ai-worker",
            [
                synthetic_metric(name, "gauge", self.now)
                for name in (
                    "worker.ai.queue.depth",
                    "worker.ai.queue.oldest",
                    "worker.ai.slot.occupied",
                    "worker.ai.circuit.open",
                    "worker.ai.queue.sample.fresh",
                    "worker.ai.queue.sample.age",
                )
            ],
        )
        expected = {
            "db_query_duration_seconds_bucket": {"pool", "operation", "le"},
            "db_pool_checked_out": {"pool"},
            "db_pool_configured_size": {"pool"},
            "sse_connections_active": set(),
            "sse_connections_closed_total": {"reason"},
            "sse_frames_total": {"kind"},
            "sse_resets_total": set(),
            "sse_delivery_lag_seconds_bucket": {"le"},
            "sse_send_duration_seconds_bucket": {"outcome", "le"},
            "worker_ai_queue_sample_fresh": set(),
            "worker_ai_queue_sample_age_seconds": set(),
            "worker_ai_queue_depth": set(),
            "worker_ai_queue_oldest_seconds": set(),
            "worker_ai_slot_occupied": set(),
            "worker_ai_circuit_open": set(),
        }
        wait_for(
            lambda: b"worker_ai_queue_sample_fresh{" in fetch(self.metrics_url + "/metrics"),
            "OPS03 metric translation",
        )
        payload = fetch(self.metrics_url + "/metrics")
        for name, dimensions in expected.items():
            for labels, _value in series(payload, name):
                require(
                    set(labels) <= RESOURCE_LABELS | dimensions,
                    "Unbounded OPS03 metric dimensions",
                )
        for forbidden in (CANARY, "private_pool", "private_operation", "/private-fake"):
            require(
                forbidden.encode() not in payload,
                "Private/unknown metric dimension escaped",
            )
        db = series(payload, "db_query_duration_seconds_bucket")
        require(
            any(
                labels.get("pool") == "core" and labels.get("operation") == "select"
                for labels, _ in db
            ),
            "Valid DB dimensions disappeared",
        )
        (self.output / "ops03-metrics.prom").write_bytes(payload)

    def prove_capacity(self) -> None:
        wait_for(
            lambda: b"system_filesystem_usage_bytes{" in fetch(self.metrics_url + "/metrics"),
            "native namespace filesystem metrics",
        )
        payload = fetch(self.metrics_url + "/metrics")
        totals: dict[str, float] = {}
        for labels, value in series(payload, "system_filesystem_usage_bytes"):
            require(
                set(labels) <= RESOURCE_LABELS | {"mountpoint", "state"},
                "Filesystem identity labels escaped",
            )
            require(
                labels.get("service_name") == "peerly-collector-capacity",
                "Filesystem service origin was not forced",
            )
            mount = labels.get("mountpoint", "")
            require(
                mount in {"/", "/var/tempo-capacity"},
                "Filesystem mount escaped namespace allowlist",
            )
            require(
                labels.get("state") in {"free", "reserved", "used"},
                "Unknown filesystem state",
            )
            totals[mount] = totals.get(mount, 0) + value
        require(
            set(totals) == {"/", "/var/tempo-capacity"},
            "Missing root or readonly WAL capacity",
        )
        require(totals["/"] > 0, "Root namespace capacity unavailable")
        require(
            totals["/var/tempo-capacity"] == WAL_BYTES,
            "WAL capacity is not the bounded fixture",
        )
        for name, destination, writable in (
            (self.collector, "/var/tempo-capacity", False),
            (self.tempo, "/var/tempo", True),
        ):
            inspected = obj(
                array(parse_json(run(["docker", "inspect", name], self.output, name + "-mounts")))[
                    0
                ]
            )
            mounts = [
                obj(item)
                for item in array(inspected["Mounts"])
                if obj(item)["Destination"] == destination
            ]
            require(len(mounts) == 1, "Missing isolated WAL mount")
            require(
                mounts[0]["RW"] is writable and mounts[0]["Name"] == self.wal_volume,
                "WAL sharing or readonly boundary differs",
            )
        (self.output / "namespace-capacity.prom").write_bytes(payload)

    def prove_traces(self) -> None:
        span = {
            "traceId": TRACE,
            "spanId": SPAN,
            "name": "GET /api/v1/me",
            "kind": 2,
            "startTimeUnixNano": str(self.now),
            "endTimeUnixNano": str(self.now + 1000000),
            "attributes": [
                {
                    "key": "request.id",
                    "value": {"stringValue": "00000000-0000-4000-8000-000000000021"},
                },
                {"key": "private.body", "value": {"stringValue": CANARY}},
            ],
            "status": {"code": 2, "message": CANARY},
            "events": [{"name": CANARY, "timeUnixNano": str(self.now)}],
        }
        db_span = {
            **span,
            "spanId": "fedcba0987654321",
            "name": "db.query",
            "kind": 3,
            "attributes": [
                {"key": "db.system", "value": {"stringValue": "postgresql"}},
                {"key": "db.pool.name", "value": {"stringValue": "core"}},
                {"key": "query.operation", "value": {"stringValue": "select"}},
                {"key": "db.statement", "value": {"stringValue": CANARY}},
            ],
        }
        fetch(
            self.otlp_url + "/v1/traces",
            {
                "resourceSpans": [
                    {
                        "resource": resource(),
                        "scopeSpans": [{"scope": {"name": "studymate"}, "spans": [span, db_span]}],
                    }
                ]
            },
        )
        wait_for(
            lambda: b"GET /api/v1/me" in fetch(self.tempo_url + "/api/traces/" + TRACE),
            "actual Tempo trace query",
        )
        trace = fetch(self.tempo_url + "/api/traces/" + TRACE)
        require(CANARY.encode() not in trace, "Private trace content escaped")
        require(
            b"db.query" in trace and b"query.operation" in trace,
            "DB query span identity disappeared",
        )
        require(b"db.statement" not in trace, "SQL statement attribute escaped")
        (self.output / "tempo-trace.json").write_bytes(trace)

    def prove_logs(self) -> None:
        formatter = FORMATTER_SOURCE
        source_env = dict(os.environ)
        source_env["PYTHONPATH"] = str(ROOT / "backend/src")
        source = subprocess.run(  # noqa: S603 - fixed interpreter and literal source.
            [str(ROOT / "backend/.venv/bin/python"), "-c", formatter],
            env=source_env,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        source.check_returncode()
        require(CANARY not in source.stdout, "Formatter leaked private content")
        (self.output / "actual-source-json.log").write_text(source.stdout)
        source_logs = [obj(parse_json(line)) for line in source.stdout.splitlines()]
        require(
            len(source_logs) == SOURCE_LOG_COUNT,
            "Expected actual HTTP and runtime-error source logs",
        )
        request_log, runtime_log = source_logs
        require(
            len(array(runtime_log["stack"])) == MAX_SAFE_STACK_FRAMES,
            "Actual formatter frame bound differs",
        )
        log = {**request_log, "password": CANARY, "upload_id": CANARY, "stack": [{"file": CANARY}]}
        expected = {text(record["request_id"]): record for record in source_logs}
        expected_services = dict.fromkeys(expected, "studymate-api")
        lines = [
            ("studymate-api", json.dumps(log)),
            ("studymate-api", json.dumps(runtime_log)),
            ("studymate-api", "not-json-" + CANARY),
            ("studymate-api", json.dumps({**log, "event": CANARY})),
        ]
        fixture = obj(parse_json((BASE / "tests/log-privacy.json").read_text()))
        require(fixture["canary"] == CANARY, "Privacy canary drift")
        for index, item in enumerate(array(fixture["cases"]), start=100):
            case = obj(item)
            identifier = str(uuid.UUID(int=index))
            candidate = {
                **{
                    key: value
                    for key, value in request_log.items()
                    if key not in {"status", "service_release"}
                },
                **obj(case["input"]),
                "request_id": identifier,
                "password": CANARY,
                "message": CANARY,
                "locals": {"secret": CANARY},
            }
            service = text(case.get("service", "studymate-api"))
            require(service in {"studymate-api", "studymate-ai-worker"}, "Unknown proof service")
            lines.append((service, json.dumps(candidate)))
            expected[identifier] = obj(case["expected"])
            expected_services[identifier] = service
        with socket.create_connection(("127.0.0.1", self.syslog_port), timeout=3) as stream:
            for service, line in lines:
                stream.sendall(
                    (
                        "<14>1 2026-11-10T00:00:00Z synthetic "
                        + service
                        + " 123 - - "
                        + line
                        + "\n"
                    ).encode()
                )
        wait_for(
            lambda: integer(obj(parse_json(fetch(self.sink_url + "/proof")))["attempts"]) > 0,
            "controlled OTLP HTTP exporter outage",
        )
        fetch(self.sink_url + "/accept")
        wait_for(
            lambda: bool(array(obj(parse_json(fetch(self.sink_url + "/proof")))["records"])),
            "bounded exporter retry recovery",
            seconds=30,
        )
        proof = obj(parse_json(fetch(self.sink_url + "/proof")))
        decoded = b"".join(
            base64.b64decode(text(obj(item)["payload"]), validate=True)
            for item in array(proof["records"])
        )
        require(b"request_completed" in decoded, "Missing sanitized event")
        require(TRACE.encode() in decoded, "Missing trace correlation")
        require(CANARY.encode() not in decoded, "Log exporter leaked private content")
        require(
            all(obj(item)["path"] == "/otlp/v1/logs" for item in array(proof["records"])),
            "Wrong OTLP path",
        )
        records = [
            record
            for item in array(proof["records"])
            for record in decoded_log_records(
                base64.b64decode(text(obj(item)["payload"]), validate=True)
            )
        ]
        bodies = [body for body, _resource in records]
        require(
            len(bodies) == len(expected), "Malformed logs escaped or valid diagnostics disappeared"
        )
        (self.output / "safe-log-bodies.json").write_text(json.dumps(bodies, indent=2))
        (self.output / "sanitized-log-export.json").write_text(json.dumps(proof, indent=2))
        for body, metadata in records:
            identifier = text(body["request_id"])
            require(identifier in expected, "Unexpected log correlation")
            check_safe_log_metadata(
                body, metadata, expected[identifier], expected_services[identifier]
            )
        (self.output / "collector-metrics-after.prom").write_bytes(
            fetch(self.self_metrics_url + "/metrics")
        )

    def prove_sdk_metrics(self) -> None:
        """Real SDK/OpenMetrics regression is part of the default CI command."""
        image = (
            "prom/prometheus@sha256:"
            "d2ab0a27783fd4ad96a8853e2847b99a0be0043687b8a5d1ebfb2dd3fa4fd1b8"
        )
        configuration = {
            "global": {"scrape_interval": "1s"},
            "scrape_configs": [
                {
                    "job_name": "peerly-app-metrics",
                    "honor_labels": False,
                    "static_configs": [{"targets": [self.prefix + "-collector:8889"]}],
                }
            ],
        }
        config_path = self.output / "sdk-prometheus.json"
        config_path.write_text(json.dumps(configuration))
        # Readable synthetic config only; no production configuration or credentials.
        self.output.chmod(0o755)
        config_path.chmod(0o644)
        name = self.prefix + "-sdk-prometheus242"
        self.owned.append(name)
        run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                "--network",
                self.network,
                *self.hardened,
                "--memory",
                "128m",
                "--tmpfs",
                "/prometheus:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001",
                "--mount",
                f"type=bind,src={config_path},dst=/proof/prometheus.json,readonly",
                "--publish",
                "127.0.0.1::9090",
                image,
                "--config.file=/proof/prometheus.json",
                "--storage.tsdb.path=/prometheus",
                "--storage.tsdb.retention.time=1h",
                "--enable-feature=exemplar-storage",
            ],
            self.output,
            "sdk-prometheus242-start",
        )
        inspected = obj(
            array(
                parse_json(
                    run(["docker", "inspect", name], self.output, "sdk-prometheus242-inspect")
                )
            )[0]
        )
        binding = obj(array(obj(obj(inspected["NetworkSettings"])["Ports"])["9090/tcp"])[0])
        require(binding["HostIp"] == "127.0.0.1", "SDK proof port escaped loopback")
        prometheus = "http://127.0.0.1:" + text(binding["HostPort"])
        wait_for(lambda: b"Ready" in fetch(prometheus + "/-/ready"), "SDK Prometheus readiness")
        proof = subprocess.run(  # noqa: S603 - fixed interpreter, owned public helper and origins.
            [
                sys.executable,
                str(BASE / "sdk_metrics.py"),
                "--otlp",
                self.otlp_url,
                "--prometheus",
                prometheus,
                "--output",
                str(self.output),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
            env={
                key: value
                for key, value in os.environ.items()
                if not key.startswith("OTEL_")
                and key.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
            },
        )
        (self.output / "sdk-helper.log").write_text(proof.stdout + proof.stderr)
        require(proof.returncode == 0, "Actual SDK exemplar proof failed; see preserved helper log")
        require(
            obj(parse_json((self.output / "sdk-result.json").read_text()))["result"] == "PASS",
            "SDK proof did not complete",
        )

    def record_success(self) -> None:
        self.report["checks"] = [
            "native collector/remote-write/Tempo/compose configuration",
            "native Prometheus rule behavior/config and dashboard expressions",
            "nonroot read-only startup",
            "actual metric names/cardinality allowlist",
            "real SDK Counter/histogram exemplars: Prometheus2.42 scrape/IDs/value/time/privacy",
            "OPS03 DB/SSE and AI sample freshness translation/privacy",
            "native namespace-only root and shared readonly bounded WAL capacity",
            "actual source JSON/RFC5424 sanitization",
            "OTLP HTTP 503/retry/recovery",
            "actual Tempo trace ingestion/query/redaction",
        ]
        self.report["result"] = "PASS"

    def cleanup(self) -> None:
        for container in reversed(self.owned):
            logs = subprocess.run(  # noqa: S603 - fixed Docker command, owned container.
                [DOCKER, "logs", container],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            (self.output / (container + "-runtime.log")).write_text(logs.stdout + logs.stderr)
            # Security failure remains a failure, never filter offending lines.
            if CANARY in logs.stdout + logs.stderr:
                self.report["result"] = "FAIL: raw canary leaked to infrastructure diagnostics"
            subprocess.run(  # noqa: S603 - fixed Docker command, owned container.
                [DOCKER, "rm", "--force", container],
                capture_output=True,
                check=True,
                timeout=20,
            )
        subprocess.run(  # noqa: S603 - fixed Docker command, owned network.
            [DOCKER, "network", "rm", self.network],
            capture_output=True,
            check=True,
            timeout=20,
        )
        if self.wal_created:
            run(
                ["docker", "volume", "rm", self.wal_volume],
                self.output,
                "bounded-wal-volume-remove",
            )
        self.report["cleanup"] = "Owned containers/network/WAL volume removed; images retained"
        self.report["seconds"] = time.monotonic() - self.started
        self.report["source_drift"] = [
            name
            for name, value in self.snapshot.items()
            if hashlib.sha256((BASE / name).read_bytes()).hexdigest() != value
        ]
        (self.output / "result.json").write_text(json.dumps(self.report, indent=2) + "\n")

    def execute(self, *, logs_only: bool = False) -> None:
        run(["docker", "network", "create", self.network], self.output, "network-create")
        try:
            self.native_configuration(logs_only=logs_only)
            if not logs_only:
                self.prometheus_rules()
                self.prometheus_configuration()
            self.start_fixtures(logs_only=logs_only)
            if not logs_only:
                self.prove_metrics()
                self.prove_ops_metrics()
                self.prove_sdk_metrics()
                self.prove_capacity()
                self.prove_traces()
            self.prove_logs()
            if logs_only:
                self.report.update(
                    scope="local actual formatter/native bounded stack/status privacy only",
                    checks=[
                        "native collector and remote-write config",
                        "actual source traceback20 and HTTP integer status",
                        "bounded safe frame adversarial cases and canary rejection",
                        "original RFC5424/OTLP503-recovery/privacy assertions",
                    ],
                    result="PASS",
                )
            else:
                self.record_success()
        finally:
            self.cleanup()
        if self.report.get("result") != "PASS" or self.report["source_drift"]:
            raise RuntimeError("OPS02 bounded proof failed; original evidence retained")
        sys.stdout.write(json.dumps(self.report, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument(
        "--logs-only", action="store_true", help="Focused source/native log privacy regression"
    )
    args = parser.parse_args()
    output = pathlib.Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    Proof(output).execute(logs_only=bool(args.logs_only))


if __name__ == "__main__":
    main()
