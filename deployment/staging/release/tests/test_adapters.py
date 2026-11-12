"""Synthetic transport contracts only; never evidence of live staging readiness."""

from __future__ import annotations

import argparse
import io
import json
import struct
import zipfile
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
import pytest
from deployment.staging.release import transport
from deployment.staging.release.cli import execute, private_write
from deployment.staging.release.data import Object, RejectedError, obj
from deployment.staging.release.metrics import METRICS, SERVICES, counters
from deployment.staging.release.portainer import DOCKER, Portainer, demultiplex
from deployment.staging.release.probes import DATABASE
from deployment.staging.release.providers import (
    RECEIPT_MARKER,
    Github,
    Registry,
    backend_log_receipt,
)
from deployment.staging.release.transport import Http, Request

if TYPE_CHECKING:
    from pathlib import Path

SHA = "b" * 40
CONFIG = "sha256:" + "c" * 64
ORIGIN = "https://portainer.example.invalid"


def test_https_only_and_single_uncertain_write() -> None:
    calls: list[httpx.Request] = []

    def fail(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("synthetic private body", request=request)

    http = Http(httpx.MockTransport(fail))
    with pytest.raises(RejectedError, match="https_endpoint"):
        http.send(Request("http://example.invalid"))
    assert not calls
    payload: Object = {
        "StackFileContent": "synthetic",
        "Env": [],
        "Prune": False,
        "PullImage": False,
    }
    with pytest.raises(RejectedError, match=r"^transport_failed_no_retry$"):
        Portainer(http, ORIGIN, "synthetic").request("/api/stacks/4?endpointId=1", payload, "PUT")
    assert len(calls) == 1


def test_body_limit_and_redirect_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            HTTPStatus.FOUND, headers={"Location": "https://other.invalid"}, content=b"x" * 64
        )

    monkeypatch.setattr(transport, "MAX_BODY", 32)
    with pytest.raises(RejectedError, match="http_body_limit"):
        Http(httpx.MockTransport(handler)).send(Request(ORIGIN))
    assert calls == [ORIGIN]


def test_portainer_prohibits_other_target_pull_and_mutation() -> None:
    def forbidden(_request: httpx.Request) -> httpx.Response:
        pytest.fail("must refuse before network")

    portainer = Portainer(Http(httpx.MockTransport(forbidden)), ORIGIN, "synthetic")
    with pytest.raises(RejectedError, match="stack_payload"):
        portainer.request("/api/stacks/5?endpointId=1", {}, "PUT")
    with pytest.raises(RejectedError, match="stack_payload"):
        portainer.request("/api/stacks/4?endpointId=1", {"PullImage": True}, "PUT")
    with pytest.raises(RejectedError, match="portainer_operation"):
        portainer.request(DOCKER + "/containers/" + "a" * 64 + "/stop", {}, "POST")
    with pytest.raises(RejectedError, match="fixed_probe_only"):
        portainer.probe("a" * 64, "arbitrary code")


def test_readonly_probe_real_docker_wire_contract() -> None:
    cid, eid = "a" * 64, "e" * 64
    output = b'{"heads":["0060_report_triage"]}'
    frame = b"\x01\0\0\0" + struct.pack(">I", len(output)) + output
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/containers/" + cid + "/exec"):
            data = json.loads(request.content)
            assert data["Cmd"] == ["python", "-c", DATABASE]
            assert data["Privileged"] is False
            assert data["User"] == "10001:10001"
            return httpx.Response(HTTPStatus.CREATED, json={"Id": eid})
        if request.url.path.endswith("/exec/" + eid + "/start"):
            assert request.method == "POST"
            return httpx.Response(HTTPStatus.OK, content=frame)
        assert request.url.path.endswith("/exec/" + eid + "/json")
        return httpx.Response(HTTPStatus.OK, json={"Running": False, "ExitCode": 0})

    result = Portainer(Http(httpx.MockTransport(handler)), ORIGIN, "synthetic").probe(cid, DATABASE)
    assert result["heads"] == ["0060_report_triage"]
    assert len(calls) == len({"create", "start", "inspect"})
    with pytest.raises(RejectedError, match="probe_stderr_or_frame"):
        demultiplex(b"\x02\0\0\0" + struct.pack(">I", 1) + b"x")


def zip_receipt() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("published.json", '{"source_sha":"' + SHA + '"}')
    return stream.getvalue()


def test_frontend_artifact_redirect_strips_github_authorization() -> None:
    name = "frontend-image-" + SHA + "-1"
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/artifacts"):
            return httpx.Response(
                HTTPStatus.OK,
                json={
                    "total_count": 1,
                    "artifacts": [
                        {
                            "id": 20,
                            "name": name,
                            "expired": False,
                            "workflow_run": {"id": 100, "head_sha": SHA},
                        }
                    ],
                },
            )
        if request.url.host == "api.github.com":
            assert request.headers.get("authorization") == "Bearer synthetic"
            return httpx.Response(
                HTTPStatus.FOUND,
                headers={
                    "Location": "https://fixture.blob.core.windows.net/archive?signature=synthetic"
                },
            )
        assert "authorization" not in request.headers
        return httpx.Response(HTTPStatus.OK, content=zip_receipt())

    run: Object = {"id": 100, "run_attempt": 1, "head_sha": SHA}
    result = Github(Http(httpx.MockTransport(handler)), "synthetic").artifact(run, name)
    assert obj(json.loads(result["published.json"]))["source_sha"] == SHA
    assert len(calls) == len({"list", "redirect", "download"})


def test_backend_log_receipt_rejects_echo_and_ambiguity() -> None:
    line = (
        "2026-11-12T19:00:00.000Z " + RECEIPT_MARKER + '{"source_sha":"' + SHA + '"}\n'
    ).encode()
    assert json.loads(backend_log_receipt(line))["source_sha"] == SHA
    for bad in [b'echo "PEERLY_BACKEND_PUBLICATION_V1={...}"\n', line + line]:
        with pytest.raises(RejectedError, match="backend_receipt_log_missing_or_ambiguous"):
            backend_log_receipt(bad)


def test_registry_config_redirect_has_no_bearer_and_uses_exact_digest() -> None:
    digest = "sha256:" + "b" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(HTTPStatus.OK, json={"token": "synthetic-bearer"})
        if "/manifests/" in request.url.path:
            assert request.url.path.endswith(digest)
            return httpx.Response(HTTPStatus.OK, json={"config": {"digest": CONFIG}})
        if request.url.host == "ghcr.io":
            assert request.headers["authorization"] == "Bearer synthetic-bearer"
            return httpx.Response(
                HTTPStatus.TEMPORARY_REDIRECT,
                headers={
                    "Location": "https://pkg-containers.githubusercontent.com/config?signature=synthetic"
                },
            )
        assert "authorization" not in request.headers
        return httpx.Response(HTTPStatus.OK, content=b'{"config":{}}')

    _, config = Registry(Http(httpx.MockTransport(handler)), "fixture", "synthetic").fetch(
        "backend", "ghcr.io/mark0000dev/peerly-backend@" + digest
    )
    assert config == b'{"config":{}}'


def metric_text(value: int, source: str = SHA) -> bytes:
    return "\n".join(
        f'{name}{{service_name="{SERVICES[role]}",service_version="{source}",'
        f'deployment_environment_name="staging",outcome="idle"}} {value}'
        for role, name in METRICS.items()
    ).encode()


def test_real_instrument_names_require_fresh_source_specific_progress() -> None:
    first = counters(metric_text(10), SHA)
    second = counters(metric_text(11), SHA)
    assert all(second[role] > first[role] for role in METRICS)
    assert not any(counters(metric_text(11, "a" * 40), SHA).values())
    assert not any(
        counters(
            metric_text(11).replace(b'outcome="idle"', b'outcome="storage_unavailable"'), SHA
        ).values()
    )


def test_new_attempt_blocked_by_prior_unknown_write(tmp_path: Path) -> None:
    private_write(tmp_path / "unresolved.json", {"attempt": "old", "sha": SHA})
    args = argparse.Namespace(operation="promote", reconcile_attempt="")
    with pytest.raises(RejectedError, match="unresolved_attempt_requires_explicit_reconciliation"):
        execute(args, SHA, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_fixed_probes_compile_without_bootstrap_or_mutation() -> None:
    from deployment.staging.release.probes import SAFETY_DATABASE

    for script in [DATABASE, SAFETY_DATABASE]:
        compile(script, "<readonly-container-probe>", "exec")
        assert "transaction(readonly=True)" in script
        assert "'default_transaction_read_only':'on'" in script
        assert "SELECT version_num FROM public.alembic_version" in script
        assert "UPDATE " not in script
        assert "DELETE " not in script
        assert "bootstrap" not in script
    assert "Settings" not in SAFETY_DATABASE


def test_successfully_rolled_back_sha_cannot_be_automatically_repromoted(tmp_path: Path) -> None:
    private_write(tmp_path / ("rolled-back-" + SHA + ".json"), {"sha": SHA})
    args = argparse.Namespace(operation="promote", reconcile_attempt="")
    with pytest.raises(RejectedError, match="rolled_back_source_requires_forward_fix"):
        execute(args, SHA, tmp_path / "new")
    assert not (tmp_path / "new").exists()
