"""External metrics differ from core-worker steps; fixed DB probes never register."""

from __future__ import annotations

import json
import struct

import httpx
import pytest
from deployment.staging.release.data import Object, RejectedError
from deployment.staging.release.external import AcceptedExternal, destinations
from deployment.staging.release.external_metrics import progressed, sample
from deployment.staging.release.external_probe import EXTERNAL_DATABASE
from deployment.staging.release.portainer import DOCKER, Portainer
from deployment.staging.release.tests.test_external import CID, actual, receipt, summary
from deployment.staging.release.transport import Http


def metrics(cycles: str = "4", age: str = "1", available: str = "1") -> bytes:
    labels = (
        'service_name="peerly-external-delivery-worker",service_version="synthetic",'
        'deployment_environment_name="staging",instance="worker"'
    )
    return (
        f'worker_external_cycles_total{{{labels},storage="available"}} {cycles}\n'
        f"worker_external_storage_available{{{labels}}} {available}\n"
        f"worker_external_cycle_age_seconds{{{labels}}} {age}\n"
    ).encode()


def test_progress_requires_completed_available_cycles_and_same_series() -> None:
    progressed(sample(metrics(), "synthetic"), sample(metrics(cycles="5"), "synthetic"))
    for body in [
        metrics(),
        metrics(cycles="0"),
        metrics(cycles="5").replace(b'"worker"', b'"other"'),
    ]:
        with pytest.raises(RejectedError, match="external_progress"):
            progressed(sample(metrics(), "synthetic"), sample(body, "synthetic"))


@pytest.mark.parametrize(
    ("cycles", "age", "available"),
    [
        ("NaN", "1", "1"),
        ("Inf", "1", "1"),
        ("4", "31", "1"),
        ("4", "-1", "1"),
        ("4", "1", "0"),
    ],
)
def test_stale_unavailable_or_invalid_samples_block(cycles: str, age: str, available: str) -> None:
    with pytest.raises(RejectedError):
        sample(metrics(cycles, age, available), "synthetic")


def test_wrong_revision_missing_storage_or_duplicate_series_block() -> None:
    for body in [
        metrics().replace(b'"synthetic"', b'"other"'),
        metrics().replace(b'storage="available"', b'outcome="idle"'),
        metrics() + metrics(),
    ]:
        with pytest.raises(RejectedError):
            sample(body, "synthetic")


@pytest.mark.parametrize("change", ["none", "database", "configured", "registered"])
def test_fixed_probe_checks_real_existing_bindings_without_writes(change: str) -> None:
    record = receipt()
    expected = record["destinations"]
    result: Object = {
        "heads": ["0060_report_triage"],
        "database_name": "peerly_staging",
        "configured": expected,
        "registered": expected,
    }
    if change == "database":
        result["database_name"] = "postgres"
    elif change == "configured":
        result["configured"] = []
    elif change == "registered":
        result["registered"] = []
    exec_id = "e" * 64
    calls: list[str] = []

    def serve(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path == DOCKER + f"/containers/{CID}/exec":
            assert request.method == "POST"
            payload = json.loads(request.content)
            assert payload["Cmd"] == ["python", "-c", EXTERNAL_DATABASE]
            assert payload["Privileged"] is False
            assert payload["User"] == "10001:10001"
            return httpx.Response(201, json={"Id": exec_id})
        if path == DOCKER + f"/exec/{exec_id}/start":
            assert request.method == "POST"
            data = json.dumps(result).encode()
            return httpx.Response(
                200, content=b"\x01\x00\x00\x00" + struct.pack(">I", len(data)) + data
            )
        assert request.method == "GET"
        if path == DOCKER + "/containers/json":
            return httpx.Response(200, json=[summary()])
        if path == DOCKER + f"/containers/{CID}/json":
            return httpx.Response(200, json=actual())
        assert path == DOCKER + f"/exec/{exec_id}/json"
        return httpx.Response(200, json={"Running": False, "ExitCode": 0})

    portainer = Portainer(
        Http(httpx.MockTransport(serve)), "https://synthetic.invalid", "synthetic"
    )
    if change == "none":
        assert destinations(portainer, AcceptedExternal.parse(record), "peerly_staging") == {
            "configured": expected,
            "registered": expected,
        }
        assert calls.count(DOCKER + f"/containers/{CID}/json") == len(["before", "after"])
    else:
        with pytest.raises(RejectedError):
            destinations(portainer, AcceptedExternal.parse(record), "peerly_staging")
