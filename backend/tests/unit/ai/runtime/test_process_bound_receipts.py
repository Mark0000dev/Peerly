"""Synthetic namespace/resource facts exercise live checks; not actual-container proof."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from studymate.infrastructure.ai.runtime.acceptance import (
    REQUIRED_PROOFS,
    ReceiptExpectation,
    RuntimeAcceptanceError,
    RuntimeReceipt,
    policy_digest,
    validate_runtime_receipt,
)
from tests.unit.ai.runtime.test_policy import pin


def receipt(pids: int) -> RuntimeReceipt:
    at = datetime.now(UTC)
    return RuntimeReceipt(
        schema_version=1,
        stage="containment",
        deployment_id=uuid4(),
        issued_at=at,
        expires_at=at + timedelta(hours=1),
        binary_sha256=pin().sha256,
        policy_sha256=policy_digest(pin(), max_processes=pids),
        boot_id=uuid4(),
        network_namespace="net:[100]",
        pid_namespace="pid:[200]",
        cgroup_membership="0::/synthetic",
        memory_max=1073741824,
        pids_max=pids,
        cpu_max="50000 100000",
        workspace_bytes=33554432,
        evidence=dict.fromkeys(REQUIRED_PROOFS, "a" * 64),
    )


def synthetic_namespace(
    monkeypatch: pytest.MonkeyPatch, proof: RuntimeReceipt, actual_pids: int
) -> None:
    original_read = Path.read_text
    original_stat = os.fstat
    facts = {
        "/proc/sys/kernel/random/boot_id": str(proof.boot_id),
        "/proc/self/cgroup": proof.cgroup_membership,
        "/sys/fs/cgroup/memory.max": str(proof.memory_max),
        "/sys/fs/cgroup/pids.max": str(actual_pids),
        "/sys/fs/cgroup/cpu.max": proof.cpu_max,
        "/proc/self/status": "NoNewPrivs:\t1\nCapEff:\t0000000000000000\n",
    }

    def read(path: Path, *args: object, **kwargs: object) -> str:
        del args, kwargs
        return facts[str(path)] if str(path) in facts else original_read(path)

    def links(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes], *, dir_fd: int | None = None
    ) -> str:
        del dir_fd
        return {
            "/proc/self/ns/net": proof.network_namespace,
            "/proc/self/ns/pid": proof.pid_namespace,
        }[str(path)]

    def metadata(fd: int) -> os.stat_result:
        value = original_stat(fd)
        return os.stat_result(
            (
                value.st_mode,
                value.st_ino,
                value.st_dev,
                value.st_nlink,
                10002,
                10002,
                value.st_size,
                value.st_atime,
                value.st_mtime,
                value.st_ctime,
            )
        )

    def volume(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> os.statvfs_result:
        flags = os.ST_RDONLY if str(path) == "/" else os.ST_NOEXEC
        return os.statvfs_result((4096, 4096, 8192, 4096, 4096, 0, 0, 0, flags, 255))

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(os, "readlink", links)
    monkeypatch.setattr(os, "fstat", metadata)
    monkeypatch.setattr(os, "geteuid", lambda: 10002)
    monkeypatch.setattr(os, "statvfs", volume)


@pytest.mark.parametrize(
    "case",
    [
        (32, 32, 32, None),
        (40, 40, 40, None),
        (40, 32, 32, "proof_mismatch"),
        (32, 40, 40, "proof_mismatch"),
        (40, 40, 32, "resource_limits_changed"),
        (32, 32, 40, "resource_limits_changed"),
    ],
)
async def test_bound_requires_matching_policy_receipt_and_live_cgroup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: tuple[int, int, int, str | None],
) -> None:
    configured, proved, actual, error = case
    proof = receipt(proved)
    path = tmp_path / "synthetic-proof.json"
    path.write_text(proof.model_dump_json())
    path.chmod(0o600)
    synthetic_namespace(monkeypatch, proof, actual)
    expectation = ReceiptExpectation(stage="containment", max_processes=configured)
    if error is not None:
        with pytest.raises(RuntimeAcceptanceError, match=error):
            await validate_runtime_receipt(path, pin(), tmp_path, expectation=expectation)
    else:
        assert (
            await validate_runtime_receipt(path, pin(), tmp_path, expectation=expectation) == proof
        )


async def test_resource_opt_in_never_waives_namespace_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proof = receipt(40)
    path = tmp_path / "synthetic-proof.json"
    path.write_text(proof.model_dump_json())
    path.chmod(0o600)
    synthetic_namespace(monkeypatch, proof, 40)
    monkeypatch.setattr(os, "readlink", lambda _path: "pid:[999]")
    with pytest.raises(RuntimeAcceptanceError, match="deployment_changed"):
        await validate_runtime_receipt(
            path,
            pin(),
            tmp_path,
            expectation=ReceiptExpectation(stage="containment", max_processes=40),
        )
