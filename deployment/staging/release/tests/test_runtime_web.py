"""Synthetic ingress/archive mismatch tests; no real readiness grant."""

from __future__ import annotations

import io
import json
import tarfile
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
import pytest
from deployment.staging.release.data import RejectedError
from deployment.staging.release.journal import Journal
from deployment.staging.release.portainer import Portainer
from deployment.staging.release.release import ORIGIN, Snapshot
from deployment.staging.release.runtime import ObservationInputs, Runtime
from deployment.staging.release.transport import Http

if TYPE_CHECKING:
    from pathlib import Path

CID = "a" * 64
SHA = "b" * 40


def archived(name: str, body: bytes) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    return stream.getvalue()


@pytest.mark.parametrize("fault", ["", "map_cache", "csr_body", "identity", "javascript"])
def test_real_web_contract_detects_wrong_ingress_bytes(fault: str, tmp_path: Path) -> None:
    release = json.dumps(
        {"releaseId": SHA, "origin": ORIGIN, "assets": [{"basename": "main.js", "assetId": 0}]}
    ).encode()
    baked = {
        "index.html": b"landing document",
        "index.csr.html": b"client document",
        "observation-release.json": release,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        path = request.url.path
        if request.url.host == "portainer.example.invalid":
            assert path.endswith("/containers/" + CID + "/archive")
            name = request.url.params["path"].rsplit("/", 1)[-1]
            return httpx.Response(HTTPStatus.OK, content=archived(name, baked[name]))
        assert request.url.host == "peerly-staging.aleksei-orlov.dev"
        if path == "/assets/observation-release.json":
            return httpx.Response(
                HTTPStatus.OK,
                content=release,
                headers={
                    "content-type": "application/json",
                    "cache-control": "max-age=100" if fault == "map_cache" else "no-cache",
                },
            )
        if path in {"/api/v1/me", "/api/v1/me/profile"}:
            if "cookie" not in request.headers:
                return httpx.Response(HTTPStatus.UNAUTHORIZED)
            return httpx.Response(
                HTTPStatus.OK,
                headers={"cache-control": "no-store"},
                json={"account_id": "wrong" if fault == "identity" else "owned-fixture"},
            )
        if path == "/main.js":
            return httpx.Response(
                HTTPStatus.OK,
                content=b"js",
                headers={
                    "content-type": "text/html"
                    if fault == "javascript"
                    else "application/javascript"
                },
            )
        body = baked["index.html"] if path == "/" else baked["index.csr.html"]
        if fault == "csr_body" and path == "/profile":
            body = baked["index.html"]
        return httpx.Response(HTTPStatus.OK, content=body, headers={"content-type": "text/html"})

    http = Http(httpx.MockTransport(handler))
    journal = Journal(tmp_path / "journal")
    inputs = ObservationInputs(
        "https://metrics.example.invalid",
        "synthetic",
        "synthetic",
        "owned-fixture",
        CID,
        "peerly_staging",
        lambda: None,
    )
    runtime = Runtime(
        Portainer(http, "https://portainer.example.invalid", "synthetic"), http, journal, {}, inputs
    )
    try:
        if fault:
            with pytest.raises(RejectedError):
                runtime.web(CID)
        else:
            assert runtime.web(CID)["releaseId"] == SHA
            url = "postgresql+asyncpg://fixture@database.invalid/peerly_staging"
            snapshot = Snapshot(
                {"Env": [{"name": "PEERLY_DATABASE_URL", "value": url}]}, "synthetic"
            )
            runtime.database_target({"Config": {"Env": ["DATABASE_URL=" + url]}}, snapshot)
            wrong = url.replace("peerly_staging", "default_db")
            with pytest.raises(RejectedError, match="database_target"):
                runtime.database_target({"Config": {"Env": ["DATABASE_URL=" + wrong]}}, snapshot)
    finally:
        journal.close()
