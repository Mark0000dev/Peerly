"""Actual external-worker storage-labelled cycles and fresh gauges, not core steps."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from deployment.staging.release.data import require
from deployment.staging.release.metrics import LABEL

CYCLES = "worker_external_cycles_total"
AVAILABLE = "worker_external_storage_available"
AGE = "worker_external_cycle_age_seconds"
FRESH_SECONDS = 30


@dataclass(frozen=True, slots=True)
class ExternalSample:
    cycles: float
    identity: tuple[tuple[str, str], ...]


def sample(body: bytes, revision: str) -> ExternalSample:
    values: dict[str, tuple[float, tuple[tuple[str, str], ...]]] = {}
    for line in body.decode().splitlines():
        if line.startswith("#") or "{" not in line:
            continue
        name, rest = line.split("{", 1)
        if name not in {CYCLES, AVAILABLE, AGE}:
            continue
        labels_raw, number = rest.split("}", 1)
        labels = {match[1]: json.loads(match[2]) for match in LABEL.finditer(labels_raw)}
        if not (
            labels.get("service_name") == "peerly-external-delivery-worker"
            and labels.get("service_version") == revision
            and labels.get("deployment_environment_name") == "staging"
        ):
            continue
        if name == CYCLES and labels.get("storage") != "available":
            continue
        value = float(number.strip().split()[0])
        require(math.isfinite(value) and value >= 0, "external_metric_value")
        require(name not in values, "external_metric_multiple_series")
        identity = tuple(sorted((k, v) for k, v in labels.items() if k != "storage"))
        values[name] = value, identity
    require(set(values) == {CYCLES, AVAILABLE, AGE}, "external_metrics_missing")
    require(
        values[AVAILABLE][0] == 1 and values[AGE][0] <= FRESH_SECONDS,
        "external_storage_or_cycle_stale",
    )
    require(
        values[CYCLES][1] == values[AVAILABLE][1] == values[AGE][1], "external_metrics_identity"
    )
    return ExternalSample(*values[CYCLES])


def progressed(before: ExternalSample, after: ExternalSample) -> None:
    require(
        before.identity == after.identity and after.cycles > before.cycles,
        "external_progress_missing_or_reset",
    )
