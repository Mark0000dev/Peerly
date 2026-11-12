"""Default-CI real SDK → Collector → Prometheus 2.42 exemplar regression.

No application startup, credentials or provider access. All network endpoints are
explicit loopback ports owned by validate.py. Source declarations and locked SDK
versions must agree with the accepted closed native mapping before export.
"""

import argparse
import ast
import importlib.metadata
import json
import math
import pathlib
import time
import tomllib
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from typing import override

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import CallbackOptions, Counter, Histogram, Observation
from opentelemetry.sdk.metrics import MeterProvider, TraceBasedExemplarFilter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, MetricExportResult, MetricsData
from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, use_span

BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parents[1]
CANARY = "PRIVATE_SDK_CANARY"
TRACE = "a" * 32
SPAN = "b" * 16
PROMETHEUS_MILLISECOND = 0.001
LABELS = frozenset(
    {
        "http.route",
        "http.response.status_code",
        "http.request.method",
        "pool",
        "operation",
        "outcome",
        "kind",
        "reason",
        "sink",
        "state",
        "storage",
    }
)
type Json = bool | int | float | str | list[Json] | dict[str, Json] | None


def checked(value: object) -> Json:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list):
        return [checked(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, Json] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Invalid JSON object key")
            result[key] = checked(item)
        return result
    raise ValueError("Invalid JSON value")


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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


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
        raise ValueError("Proof redirects forbidden")


def origin(value: str) -> str:
    url = urllib.parse.urlsplit(value)
    if (
        url.scheme != "http"
        or url.hostname != "127.0.0.1"
        or url.port is None
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.path not in ("", "/")
    ):
        raise ValueError("Expected explicit loopback origin")
    return value.rstrip("/")


def fetch(url: str) -> Json:
    # Origin is independently checked even for internally generated query paths.
    parsed = urllib.parse.urlsplit(url)
    origin(urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", "")))
    request = urllib.request.Request(url)  # noqa: S310 - strict loopback validation above.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=3) as response:
        data = response.read(4 * 1024 * 1024 + 1)
    require(len(data) <= 4 * 1024 * 1024, "Proof response too large")
    value: object = json.loads(data)
    return checked(value)


@dataclass(frozen=True, slots=True)
class Instrument:
    name: str
    kind: str
    unit: str
    prometheus: str


def declarations() -> list[Instrument]:
    fixture: object = json.loads((BASE / "tests/sdk-metrics.json").read_text())
    items = [obj(item) for item in array(obj(checked(fixture))["source_instruments"])]
    expected = [
        Instrument(*(text(item[key]) for key in ("name", "kind", "unit", "prometheus")))
        for item in items
    ]
    found: set[tuple[str, str, str]] = set()
    files = sorted((ROOT / "backend/src/studymate/infrastructure/observability").glob("*.py"))
    files.append(ROOT / "backend/src/studymate/infrastructure/ai/telemetry.py")
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            kind = node.func.attr.removeprefix("create_")
            if kind not in {"counter", "histogram", "observable_gauge"}:
                continue
            require(
                bool(node.args) and isinstance(node.args[0], ast.Constant),
                "Instrument names must remain explicit source declarations",
            )
            first = node.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                raise ValueError("Invalid source instrument name")
            unit = ""
            for keyword in node.keywords:
                if keyword.arg == "unit":
                    require(isinstance(keyword.value, ast.Constant), "Nonliteral source unit")
                    if isinstance(keyword.value, ast.Constant) and isinstance(
                        keyword.value.value, str
                    ):
                        unit = keyword.value.value
            found.add((first.value, kind, unit))
    require(
        found == {(i.name, i.kind, i.unit) for i in expected},
        "Source instruments drifted from closed native mapping",
    )
    project = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())
    for package in ("opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-http"):
        version = importlib.metadata.version(package)
        require(
            package + "==" + version in project["project"]["dependencies"],
            "Installed SDK differs from locked source version",
        )
    return expected


@dataclass(frozen=True, slots=True)
class ExemplarSample:
    name: str
    value: float
    timestamp: float


def exemplar_samples(data: MetricsData) -> list[ExemplarSample]:
    result = []
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                for point in metric.data.data_points:
                    for exemplar in point.exemplars:
                        require(
                            exemplar.trace_id == int(TRACE, 16)
                            and exemplar.span_id == int(SPAN, 16),
                            "SDK sample not correlated",
                        )
                        require(
                            exemplar.filtered_attributes is not None
                            and exemplar.filtered_attributes.get("private.raw") == CANARY,
                            "SDK View did not exercise private exemplar attributes",
                        )
                        result.append(
                            ExemplarSample(
                                metric.name, float(exemplar.value), exemplar.time_unix_nano / 1e9
                            )
                        )
    return result


class Producer:
    def __init__(self, endpoint: str, instruments: list[Instrument], service: str) -> None:
        self.reader = InMemoryMetricReader()
        self.provider = MeterProvider(
            metric_readers=[self.reader],
            resource=Resource({"service.name": service, "service.version": "sdk-ci-proof"}),
            exemplar_filter=TraceBasedExemplarFilter(),
            views=[View(instrument_name="*", attribute_keys=set(LABELS))],
        )
        self.exporter = OTLPMetricExporter(endpoint=endpoint + "/v1/metrics", timeout=2)
        meter = self.provider.get_meter("peerly.synthetic-sdk-proof")
        self.counters: list[Counter] = []
        self.histograms: list[Histogram] = []
        self.attributes: dict[str, str | int] = {
            "http.route": "/api/v1/me",
            "http.response.status_code": 200,
            "http.request.method": "GET",
            "pool": "core",
            "operation": "select",
            "outcome": "succeeded",
            "kind": "change",
            "reason": "transient",
            "sink": "umami",
            "state": "pending",
            "storage": "available",
            "private.raw": CANARY,
        }
        for item in instruments:
            if item.kind == "counter":
                self.counters.append(meter.create_counter(item.name, unit=item.unit))
            elif item.kind == "histogram":
                self.histograms.append(meter.create_histogram(item.name, unit=item.unit))
            else:
                meter.create_observable_gauge(item.name, unit=item.unit, callbacks=[self.gauge])

    def gauge(self, options: CallbackOptions) -> Iterable[Observation]:
        del options
        return (Observation(1, self.attributes),)

    def export(self) -> list[ExemplarSample]:
        span = NonRecordingSpan(
            SpanContext(
                trace_id=int(TRACE, 16),
                span_id=int(SPAN, 16),
                is_remote=False,
                trace_flags=TraceFlags(1),
            )
        )
        with use_span(span):
            for counter in self.counters:
                counter.add(3, self.attributes)
            for histogram in self.histograms:
                histogram.record(0.25, self.attributes)
        data = self.reader.get_metrics_data()
        require(data is not None, "SDK produced no metrics")
        if data is None:
            raise RuntimeError("SDK produced no metrics")
        samples = exemplar_samples(data)
        require(self.exporter.export(data) == MetricExportResult.SUCCESS, "SDK OTLP export failed")
        return samples

    def close(self) -> None:
        self.provider.shutdown()
        self.exporter.shutdown()


class Scenario:
    def __init__(self, otlp: str, prometheus: str, output: pathlib.Path) -> None:
        self.otlp = origin(otlp)
        self.prometheus = origin(prometheus)
        self.output = output
        self.instruments = declarations()
        self.producers: list[Producer] = []
        self.samples: list[ExemplarSample] = []

    def query(self, expression: str) -> list[Json]:
        value = obj(
            fetch(
                self.prometheus + "/api/v1/query?" + urllib.parse.urlencode({"query": expression})
            )
        )
        require(value["status"] == "success", "Prometheus query failed")
        return array(obj(value["data"])["result"])

    def ready(self) -> bool:
        # Query all canonical selectors; the last-error scrape failure is never ignored.
        for instrument in self.instruments:
            name = instrument.prometheus + ("_count" if instrument.kind == "histogram" else "")
            if not self.query(name + '{job="peerly-app-metrics",service_version="sdk-ci-proof"}'):
                return False
        return True

    def check_exemplars(self) -> None:
        selector = '{job="peerly-app-metrics",service_version="sdk-ci-proof"}'
        expected_names = {
            i.prometheus + ("_bucket" if i.kind == "histogram" else ""): i.name
            for i in self.instruments
            if i.kind != "observable_gauge"
        }
        value = obj(
            fetch(
                self.prometheus
                + "/api/v1/query_exemplars?"
                + urllib.parse.urlencode({"query": selector, "start": 0, "end": time.time() + 1})
            )
        )
        self.output.joinpath("sdk-prom-exemplars.json").write_text(json.dumps(value, indent=2))
        entries = [obj(item) for item in array(value["data"])]
        names = {text(obj(entry["seriesLabels"])["__name__"]) for entry in entries}
        require(
            names == set(expected_names),
            "Every sampled SDK counter/histogram must retain exemplars",
        )
        for entry in entries:
            name = expected_names[text(obj(entry["seriesLabels"])["__name__"])]
            for item in array(entry["exemplars"]):
                exemplar = obj(item)
                require(
                    exemplar["labels"] == {"trace_id": TRACE, "span_id": SPAN},
                    "Private exemplar labels leaked or correlation changed",
                )
                raw_time = exemplar["timestamp"]
                require(isinstance(raw_time, int | float), "Invalid exemplar time")
                if not isinstance(raw_time, int | float):
                    raise ValueError("Invalid exemplar time")
                amount = float(text(exemplar["value"]))
                require(
                    math.isfinite(amount)
                    and any(
                        s.name == name
                        and s.value == amount
                        and abs(s.timestamp - raw_time) < PROMETHEUS_MILLISECOND
                        for s in self.samples
                    ),
                    "Exemplar value/time differs from actual SDK sample",
                )

    def execute(self) -> None:
        try:
            for service in (
                "studymate-api",
                "studymate-ai-worker",
                "peerly-external-delivery-worker",
            ):
                instruments = [
                    i
                    for i in self.instruments
                    if (
                        "studymate-ai-worker"
                        if i.name.startswith("worker.ai.")
                        else "peerly-external-delivery-worker"
                        if i.name.startswith("worker.external.")
                        else "studymate-api"
                    )
                    == service
                ]
                producer = Producer(self.otlp, instruments, service)
                self.producers.append(producer)
                self.samples.extend(producer.export())
            require(bool(self.samples), "No sampled SDK exemplars")
            deadline = time.monotonic() + 20
            while not self.ready():
                require(time.monotonic() < deadline, "Actual SDK Prometheus scrape failed")
                time.sleep(0.25)
            targets = fetch(self.prometheus + "/api/v1/targets")
            self.output.joinpath("sdk-prom-targets.json").write_text(json.dumps(targets, indent=2))
            for item in array(obj(obj(targets)["data"])["activeTargets"]):
                require(
                    obj(item)["health"] == "up" and obj(item)["lastError"] == "",
                    "Prometheus scrape target is not healthy",
                )
            self.check_exemplars()
            self.output.joinpath("sdk-result.json").write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "instruments": len(self.instruments),
                        "sdk_exemplars": len(self.samples),
                        "trace_id": TRACE,
                        "span_id": SPAN,
                        "privacy": "filtered_attributes empty; original IDs/value/time retained",
                    },
                    indent=2,
                )
            )
        finally:
            for producer in reversed(self.producers):
                producer.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--otlp", required=True)
    parser.add_argument("--prometheus", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    Scenario(str(args.otlp), str(args.prometheus), pathlib.Path(args.output)).execute()


if __name__ == "__main__":
    main()
