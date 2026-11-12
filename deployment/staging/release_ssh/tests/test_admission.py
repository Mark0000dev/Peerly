"""Synthetic API/source fixtures, not deployment-readiness evidence."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import struct
from typing import TYPE_CHECKING

import pytest
from deployment.staging.release_ssh.broker import (
    INPUT_NAMES,
    MANIFEST,
    REPO,
    TOOL_PATHS,
    AdmissionError,
    Github,
    Request,
    admission,
    host_inputs,
    service_arguments,
)
from deployment.staging.release_ssh.client import ssh_arguments, validate_material

if TYPE_CHECKING:
    from pathlib import Path

SHA = "a" * 40
OTHER = "b" * 40


def body() -> dict[str, object]:
    return {
        "protocol": 1,
        "operation": "promote",
        "source_sha": SHA,
        "run_id": 123,
        "run_attempt": 1,
        "recovery_attempt": "",
        "reconcile_attempt": "",
        "compatible_schema": "",
        "github_token": "synthetic-token",
    }


def request(value: dict[str, object]) -> Request:
    return Request.parse(json.dumps(value).encode())


@pytest.mark.parametrize(
    "delta",
    [
        {"command": "sh"},
        {"env": {"PATH": "bad"}},
        {"operation": "migrate"},
        {"source_sha": "refs/pull/1/head"},
        {"run_id": True},
        {"run_attempt": -1},
        {"recovery_attempt": "../../secrets"},
        {"github_token": "unsafe\nheader"},
        {"protocol": True},
        {"reconcile_attempt": "1-1"},
    ],
)
def test_closed_request(delta: dict[str, object]) -> None:
    with pytest.raises(AdmissionError):
        request(body() | delta)


def test_recovery_and_duplicate_keys(tmp_path: Path) -> None:
    value = body() | {
        "operation": "reconcile",
        "recovery_attempt": "99-1",
        "reconcile_attempt": "122-1",
        "compatible_schema": "0060_report_triage",
    }
    result = request(value)
    argv = result.cli_arguments(tmp_path)
    assert str(tmp_path / "99-1/recovery.private.json") in argv
    assert result.github_token not in argv
    with pytest.raises(AdmissionError):
        request(value | {"compatible_schema": "head"})
    with pytest.raises(AdmissionError, match="duplicate_json_key"):
        Request.parse(b'{"protocol":1,"protocol":1}')


def test_mark_admission_and_host_input_scope() -> None:
    value = {
        "repository": "Mark0000dev/Peerly",
        "environment": "internal-staging",
        "branch": "main",
        "approved_by": "Mark0000dev",
        "environment_main_only_verified": True,
        "host_key_pinned_verified": True,
    }
    admission(value)
    with pytest.raises(AdmissionError):
        admission(value | {"environment_main_only_verified": False})
    inputs: dict[str, object] = dict.fromkeys(INPUT_NAMES, "synthetic")
    inputs["PEERLY_RELEASE_STATE_DIR"] = "/var/lib/peerly-release"
    assert host_inputs(inputs)["PEERLY_RELEASE_STATE_DIR"] == "/var/lib/peerly-release"
    with pytest.raises(AdmissionError):
        host_inputs(inputs | {"LD_PRELOAD": "bad"})
    with pytest.raises(AdmissionError):
        host_inputs(inputs | {"PEERLY_RELEASE_STATE_DIR": "/var/lib/other-lock"})


def test_fixed_cgroup_service_has_no_token_arguments() -> None:
    obj = request(body())
    argv = service_arguments(obj)
    assert "--property=KillMode=control-group" in argv
    assert "--property=RuntimeMaxSec=1200" in argv
    assert "--property=NoNewPrivileges=yes" in argv
    assert "--setenv" not in " ".join(argv)
    assert obj.github_token not in " ".join(argv)
    assert argv[-1] == "--worker"


def test_pinned_host_key_and_closed_ssh_options(tmp_path: Path) -> None:
    host = "staging.example.invalid"
    blob = (
        struct.pack(">I", len(b"ssh-ed25519")) + b"ssh-ed25519" + struct.pack(">I", 32) + bytes(32)
    )
    known = host + " ssh-ed25519 " + base64.b64encode(blob).decode()
    private = "-----BEGIN OPENSSH PRIVATE KEY-----\nsynthetic\n-----END OPENSSH PRIVATE KEY-----\n"
    validate_material(host, known, private)
    argv = ssh_arguments(host, tmp_path / "agent.sock", tmp_path / "known_hosts")
    assert private not in " ".join(argv)
    assert known not in " ".join(argv)
    assert "-oStrictHostKeyChecking=yes" in argv
    assert "-oIdentityFile=none" in argv
    assert "-oForwardAgent=no" in argv
    assert argv[-1] == "peerly-staging-release-v1"
    with pytest.raises(AdmissionError):
        validate_material("-oProxyCommand=bad", known, private)
    with pytest.raises(AdmissionError):
        validate_material(host, known.replace(host, "other.invalid"), private)


class Metadata(Github):
    def __init__(self, run: dict[str, object]) -> None:
        super().__init__("synthetic")
        self.run = run

    async def get(self, path: str) -> dict[str, object]:
        if "/actions/workflows/" in path:
            return {
                "workflow_runs": [
                    {
                        "path": ".github/workflows/staging-release-quality.yml",
                        "head_sha": SHA,
                        "head_branch": "main",
                        "event": "push",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            }
        assert path == REPO + "/actions/runs/123"
        return self.run


def run_metadata() -> dict[str, object]:
    return {
        "id": 123,
        "run_attempt": 1,
        "path": ".github/workflows/staging-release.yml",
        "head_sha": SHA,
        "head_branch": "main",
        "status": "in_progress",
        "event": "workflow_run",
        "repository": {"full_name": "Mark0000dev/Peerly"},
        "head_repository": {"full_name": "Mark0000dev/Peerly"},
        "actor": {"login": "Mark0000dev"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "delta",
    [
        {"head_branch": "feature"},
        {"head_sha": OTHER},
        {"status": "completed"},
        {"event": "pull_request"},
        {"run_attempt": 2},
        {"path": ".github/workflows/other.yml"},
        {"head_repository": {"full_name": "another/Peerly"}},
    ],
)
async def test_untrusted_deployment_run(delta: dict[str, object]) -> None:
    with pytest.raises(AdmissionError):
        await Metadata(run_metadata() | delta).admit_run(request(body()), SHA)


@pytest.mark.asyncio
async def test_main_api_fields_and_quality() -> None:
    assert await Metadata(run_metadata()).admit_run(request(body()), SHA) == "Mark0000dev"


class Source(Github):
    def __init__(self, changed: bool = False, moved: bool = False) -> None:
        super().__init__("synthetic")
        self.objects: dict[str, bytes] = {}
        self.tree: list[dict[str, object]] = []
        hashes = {}
        for name in sorted(TOOL_PATHS):
            raw = name.encode()
            hashes[name] = hashlib.sha256(raw).hexdigest()
            self.add(name, raw + b"x" if changed and name.endswith("cli.py") else raw)
        self.add(MANIFEST, json.dumps({"format": 1, "files": hashes}).encode())
        self.moved = moved

    def add(self, name: str, raw: bytes) -> None:
        sha = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
        ).hexdigest()
        self.objects[sha] = raw
        self.tree.append({"path": name, "sha": sha, "mode": "100644", "type": "blob"})

    async def get(self, path: str) -> dict[str, object]:
        if "/git/trees/" in path:
            return {"truncated": False, "tree": self.tree}
        if "/branches/main" in path:
            return {"commit": {"sha": OTHER if self.moved else SHA}}
        raw = self.objects[path.rsplit("/", 1)[-1]]
        return {"encoding": "base64", "content": base64.b64encode(raw).decode()}


def file_names(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


@pytest.mark.asyncio
async def test_fetch_hash_bound_main_only(tmp_path: Path) -> None:
    await Source().fetch_tool(SHA, tmp_path)
    assert await asyncio.to_thread(file_names, tmp_path) == TOOL_PATHS


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["changed", "moved", "symlink", "scope", "native_pending"])
async def test_source_drift(tmp_path: Path, fault: str) -> None:
    source = Source(changed=fault == "changed", moved=fault == "moved")
    if fault == "symlink":
        source.tree[0]["mode"] = "120000"
    if fault == "native_pending":
        source.tree.append(
            {
                "path": "backend/migrations/versions/0061_native_login.py",
                "sha": OTHER,
                "mode": "100644",
                "type": "blob",
            }
        )
    if fault == "scope":
        source.tree = [item for item in source.tree if item["path"] != MANIFEST]
    with pytest.raises(AdmissionError):
        await source.fetch_tool(SHA, tmp_path)


class CalledQuality(Metadata):
    async def get(self, path: str) -> dict[str, object]:
        if "/actions/workflows/" in path:
            return {"workflow_runs": []}
        if "/attempts/" in path:
            return {
                "total_count": 1,
                "jobs": [
                    {
                        "name": "Release tool quality / Staging release strict offline quality",
                        "status": "completed",
                        "conclusion": "success",
                        "head_sha": SHA,
                        "run_id": 123,
                    }
                ],
            }
        return await super().get(path)


@pytest.mark.asyncio
async def test_unrelated_main_changes_use_same_deployment_quality_job() -> None:
    assert await CalledQuality(run_metadata()).admit_run(request(body()), SHA) == "Mark0000dev"
