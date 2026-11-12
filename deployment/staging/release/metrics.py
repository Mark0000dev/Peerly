"""Read actual existing collector counters, including idle worker iterations."""

from __future__ import annotations

import json
import math
import re

from deployment.staging.release.data import require

METRICS = {
    "email": "worker_email_steps_total",
    "media": "worker_media_steps_total",
    "requests": "worker_requests_expiry_steps_total",
    "changes": "worker_changes_steps_total",
}
SERVICES = {
    "email": "studymate-email-worker",
    "media": "studymate-media-worker",
    "requests": "peerly-requests-worker",
    "changes": "peerly-changes-worker",
}
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)=("(?:[^"\\]|\\.)*")')
SUCCESS = {"idle", "changed", "delivered", "ready", "cleaned"}


def counters(body: bytes, release: str) -> dict[str, float]:
    result = dict.fromkeys(METRICS, 0.0)
    for line in body.decode().splitlines():
        if line.startswith("#") or "{" not in line:
            continue
        name, rest = line.split("{", 1)
        if name not in METRICS.values():
            continue
        labels_raw, number = rest.split("}", 1)
        labels = {m[1]: json.loads(m[2]) for m in LABEL.finditer(labels_raw)}
        require(isinstance(labels.get("outcome"), str), "metric_labels")
        if (
            labels.get("service_version") != release
            or labels.get("deployment_environment_name") != "staging"
        ):
            continue
        if labels.get("outcome") not in SUCCESS:
            continue
        value = float(number.strip().split()[0])
        require(math.isfinite(value) and value >= 0, "metric_value")
        for role, metric in METRICS.items():
            if name == metric and labels.get("service_name") == SERVICES[role]:
                result[role] += value
    return result
