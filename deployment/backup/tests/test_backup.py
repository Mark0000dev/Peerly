"""Synthetic local files and typed provider doubles, never PG/S3/encryption acceptance."""

import hashlib
import json
import os
import shutil
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import pytest
from deployment.backup import run_backup as backup
from deployment.backup import streaming
from deployment.backup.retention import Retention, VerifiedRun
from deployment.backup.retention import plan as retention_plan
from deployment.restore import capture_backup as capture
from deployment.restore.accept_restore import MAX_DUMP_BYTES, MAX_JSON, REQUIRED, digest


class DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


ROOT_KEY = "retained/11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222/"
CONFIG = b"""[media_s3]
type=s3
env_auth=false
access_key_id=synthetic-identifier-not-real
secret_access_key=synthetic-value-not-real
endpoint=https://objects.example.test
[source_media]
type=alias
remote=media_s3:synthetic-media
[backup_s3]
type=s3
env_auth=false
access_key_id=synthetic-identifier-not-real
secret_access_key=synthetic-value-not-real
endpoint=https://objects.example.test
[backup_crypt]
type=crypt
remote=backup_s3:synthetic-backup/business-backups/crypt-v1
filename_encryption=standard
directory_name_encryption=true
password=synthetic-obscured-fixture-only
password2=synthetic-distinct-fixture-only
"""


def private_file(root: Path, name: str, content: bytes) -> int:
    file = root / name
    file.write_bytes(content)
    file.chmod(0o600)
    return os.open(file, os.O_RDONLY)


class Boundaries:
    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = tmp
        self.remote: dict[str, bytes] = {}
        self.calls: list[tuple[str, ...]] = []
        self.failure = ""
        self.data = {
            ROOT_KEY + "original": b"synthetic-original",
            ROOT_KEY + "photo.jpg": b"synthetic-display",
        }
        state = tmp / "state"
        state.mkdir(mode=0o700)
        binary = Path(sys.executable).resolve()
        module = capture.__file__
        assert isinstance(module, str)
        self.plan = backup.Plan(
            state,
            digest(Path(module), MAX_JSON),
            binary,
            capture.binary_hash(binary),
            "synthetic-business-generation",
            "synthetic-escrow-drill",
            8 * 1024**3,
            Retention(14, 8, 12),
        )
        req = {
            "destination": str(tmp / "never-used"),
            "psql": str(binary),
            "pg_dump": str(binary),
            "host": "source.example.test",
            "endpoint_address": "192.0.2.1",
            "port": 5432,
            "server_address": "10.20.30.40",
            "server_port": 5432,
            "database": "synthetic_source",
            "role": "synthetic_reader",
            "database_oid": "12345",
            "major": 16,
            "system_identifier": None,
            "head": "0060_report_triage",
            "sslmode": "disable",
            "plaintext_approval": "synthetic-exact-source-approval",
        }
        self.fds = [
            private_file(tmp, "request", json.dumps(req).encode()),
            private_file(tmp, "pass", b"synthetic-only"),
            private_file(tmp, "rclone", CONFIG),
        ]
        monkeypatch.setattr(capture, "capture", self.capture)
        monkeypatch.setattr(backup, "native", self.native)
        monkeypatch.setattr(streaming, "remote_listing", self.remote_listing)
        monkeypatch.setattr(streaming, "remote_hashes", self.remote_hashes)
        monkeypatch.setattr(
            shutil,
            "disk_usage",
            lambda _path: DiskUsage(16 * 1024**3, 0, 16 * 1024**3),
        )

    async def capture(
        self, request: capture.Request, _password_fd: int, _ca_fd: int | None
    ) -> None:
        request.destination.mkdir(mode=0o700)
        if self.failure == "capture":
            raise backup.BackupError("synthetic_capture_failed")
        objects = [
            {"key": key, "size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
            for key, value in self.data.items()
        ]
        value = {
            "format": 1,
            "heads": ["0060_report_triage"],
            "tables": {name: {"rows": 1, "sha256": "a" * 64} for name in REQUIRED},
            "broken_relationships": 0,
            "unvalidated_constraints": 0,
            "disabled_triggers": 0,
            "objects": objects,
        }
        capture.save(request.destination / "source.dump", b"PGDMPsynthetic-not-a-real-backup")
        capture.save(request.destination / "baseline.json", json.dumps(value).encode())
        receipt = {
            "database_capture_complete": True,
            "source_dump_sha256": digest(request.destination / "source.dump", MAX_DUMP_BYTES),
            "baseline_sha256": digest(request.destination / "baseline.json", MAX_JSON),
        }
        capture.save(request.destination / "complete.json", json.dumps(receipt).encode())

    async def native(self, _plan: backup.Plan, _descriptor: int, args: tuple[str, ...]) -> bytes:
        self.calls.append(args)
        if args == ("version",):
            return b"rclone v1.76.0\nsynthetic-native-boundary\n"
        return self.transfer(args)

    def transfer(self, args: tuple[str, ...]) -> bytes:
        action, source, target = args[:3]
        if source == "source_media:":
            for key, value in self.data.items():
                path = Path(target) / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"X" * len(value) if self.failure == "media" else value)
        elif action == "copy" and source.startswith("backup_crypt:"):
            keys = Path(args[args.index("--files-from-raw") + 1]).read_text().splitlines()
            for key in keys:
                path = Path(target) / key
                path.parent.mkdir(parents=True, exist_ok=True)
                value = self.remote[source + "/" + key]
                path.write_bytes(
                    b"bad-readback" if self.failure in {"readback", "tamper"} else value
                )
        elif action == "copy":
            if self.failure == "upload":
                raise backup.BackupError("synthetic_upload_failed")
            for file in Path(source).rglob("*"):
                if file.is_file():
                    self.remote[target + "/" + str(file.relative_to(source))] = file.read_bytes()
        elif action == "copyto" and source.startswith("backup_crypt:"):
            Path(target).write_bytes(self.remote[source])
        else:
            if self.failure == "commit":
                raise backup.BackupError("synthetic_commit_uncertain")
            self.remote[target] = Path(source).read_bytes()
        return b""

    async def remote_listing(
        self, _plan: backup.Plan, _descriptor: int, args: tuple[str, ...]
    ) -> bytes:
        if self.failure == "wrongkey":
            return b"[]"
        root = args[1]
        selected = "--include=/COMMITTED.json" in args
        items = []
        for key, value in self.remote.items():
            if key.startswith(root + "/"):
                name = key[len(root) + 1 :]
                if not selected or name == "COMMITTED.json":
                    items.append({"Path": name, "Size": len(value), "IsDir": False})
        return json.dumps(items).encode()

    async def remote_hashes(
        self,
        _plan: backup.Plan,
        _descriptor: int,
        args: tuple[str, ...],
        expected: dict[str, streaming.Expected],
    ) -> None:
        state = streaming.Hashes(expected)
        for name in expected:
            value = self.remote[args[2] + "/" + name]
            hashed = hashlib.sha256(
                b"bad" if self.failure in {"readback", "tamper"} else value
            ).hexdigest()
            state.line((hashed + "  " + name + "\n").encode())
        state.finish(9 if self.failure == "partial_hash" else 0)

    async def run(self) -> None:
        try:
            await backup.run(self.plan, self.fds[0], self.fds[1], self.fds[2], None)
        finally:
            for descriptor in self.fds:
                os.close(descriptor)


async def test_verified_readback_precedes_remote_commit_and_success_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Boundaries(tmp_path, monkeypatch)
    await case.run()
    actions = [args[0] for args in case.calls]
    assert actions == ["version", "copy", "copy", "copyto"]
    assert len(list((case.plan.state / "catalog").glob("*.json"))) == 1
    assert list((case.plan.state / "spool").iterdir()) == []
    assert json.loads((case.plan.state / "last-result.json").read_text())["success"] is True
    proposal = json.loads((case.plan.state / "retention-plan.json").read_text())
    assert proposal["remote_deletion_enabled"] is False
    for args in case.calls:
        assert args[0] not in {"delete", "purge", "sync", "move"}
        assert not any("synthetic-obscured" in arg for arg in args)
    assert any(key.endswith("/COMMITTED.json") for key in case.remote)


@pytest.mark.parametrize(
    "failure",
    ["capture", "media", "upload", "readback", "commit", "wrongkey", "tamper", "partial_hash"],
)
async def test_partial_failure_never_enters_verified_catalog_or_deletes_spool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    case = Boundaries(tmp_path, monkeypatch)
    case.failure = failure
    with pytest.raises(
        (backup.BackupError, streaming.ReadbackError),
        match=r"synthetic|media_mismatch|hash_mismatch|listing_missing|hash_command_failed",
    ):
        await case.run()
    assert not (case.plan.state / "catalog").exists()
    status = json.loads((case.plan.state / "last-result.json").read_text())
    assert status["success"] is False
    assert status["last_verified_at"] is None
    runs = list((case.plan.state / "spool").iterdir())
    assert len(runs) == 1
    assert (runs[0] / "FAILED.json").exists()
    assert not any(key.endswith("/COMMITTED.json") for key in case.remote)


def test_secret_descriptor_is_private_immutable_and_original_offset_unchanged(
    tmp_path: Path,
) -> None:
    original = private_file(tmp_path, "input", b"synthetic-not-real-credentials")
    (tmp_path / "input").chmod(0o400)
    sealed = backup.sealed_input(original)
    try:
        assert os.pread(sealed, 100, 0) == b"synthetic-not-real-credentials"
        assert os.lseek(original, 0, os.SEEK_CUR) == 0
        with pytest.raises(PermissionError, match="Operation not permitted"):
            os.write(sealed, b"tamper")
    finally:
        os.close(sealed)
        os.close(original)


@pytest.mark.parametrize(
    "replacement",
    [
        (b"type=crypt", b"type=alias"),
        (b"filename_encryption=standard", b"filename_encryption=off"),
        (b"https://", b"http://"),
        (b"env_auth=false", b"env_auth=true"),
        (b"/business-backups/crypt-v1", b"/ingest"),
    ],
)
def test_noncrypt_ambient_insecure_or_telemetry_targets_are_refused(
    tmp_path: Path,
    replacement: tuple[bytes, bytes],
) -> None:
    fd = private_file(tmp_path, "config", CONFIG.replace(*replacement))
    try:
        with pytest.raises(backup.BackupError, match=r"crypt_required|explicit_https_s3_required"):
            backup.crypt_config(fd)
    finally:
        os.close(fd)


async def test_no_overlap_lock_does_not_modify_existing_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Boundaries(tmp_path, monkeypatch)
    lock = backup.state_lock(case.plan)
    try:
        with pytest.raises(BlockingIOError):
            await case.run()
        assert case.calls == []
    finally:
        os.close(lock)


def test_retention_keeps_recent_generations_in_utc_without_deletion() -> None:
    now = datetime(2026, 11, 13, tzinfo=UTC)
    runs = tuple(VerifiedRun(f"synthetic-{day}", now - timedelta(days=day)) for day in range(90))
    result = retention_plan(runs, Retention(14, 8, 12))
    assert result["remote_deletion_enabled"] is False
    keep = result["keep"]
    assert isinstance(keep, list)
    assert "synthetic-0" in keep
    assert "synthetic-13" in keep
    assert result["review_candidates"]
    assert result["unknown_or_uncommitted_prefixes"] == "never_delete_automatically"


@pytest.mark.parametrize("value", [0, -1, 366, True])
def test_retention_requires_real_bounded_owner_counts(value: int) -> None:
    with pytest.raises(ValueError, match="retention_bounds"):
        Retention(value, 8, 12)


def test_secret_descriptor_rejects_world_readable_file(tmp_path: Path) -> None:
    descriptor = private_file(tmp_path, "input", b"synthetic")
    (tmp_path / "input").chmod(0o644)
    try:
        with pytest.raises(backup.BackupError, match="credential_metadata"):
            backup.sealed_input(descriptor)
    finally:
        os.close(descriptor)


def test_retention_rejects_naive_timestamps_instead_of_inventing_zone() -> None:
    with pytest.raises(ValueError, match="aware_retention_time_required"):
        retention_plan((VerifiedRun("synthetic", datetime(2026, 1, 1)),), Retention(14, 8, 12))


def test_unknown_transfer_action_cannot_enable_remote_deletion() -> None:
    with pytest.raises(backup.BackupError, match="transfer_action"):
        backup.transfer_args("purge", "backup_crypt:", "synthetic", None, 1000)


def test_failed_new_attempt_preserves_last_verified_age(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    plan = backup.Plan(
        state,
        "a" * 64,
        Path("/usr/bin/rclone"),
        "b" * 64,
        "synthetic-generation",
        "synthetic-drill",
        8 * 1024**3,
        Retention(14, 8, 12),
    )
    backup.result_status(plan, True, "synthetic-good")
    previous = json.loads((state / "last-verified.json").read_text())["verified_at"]
    backup.result_status(plan, False, "synthetic-failed")
    result = json.loads((state / "last-result.json").read_text())
    assert result["success"] is False
    assert result["last_verified_at"] == previous


def test_quarantine_capacity_fails_instead_of_deleting_old_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Boundaries(tmp_path, monkeypatch)
    spool = case.plan.state / "spool"
    spool.mkdir()
    for index in range(backup.MAX_QUARANTINED_RUNS):
        (spool / ("20261113T000000Z-" + f"{index:032x}")).mkdir()
    try:
        with pytest.raises(backup.BackupError, match="quarantine_full"):
            backup.local_capacity(case.plan)
        assert len(list(spool.iterdir())) == backup.MAX_QUARANTINED_RUNS
    finally:
        for descriptor in case.fds:
            os.close(descriptor)


def test_v2_capacity_accepts_known_3_point_7_gib_without_quota_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Boundaries(tmp_path, monkeypatch)
    case.plan = replace(case.plan, max_spool_bytes=3758096384)
    free = int(3.7 * 1024**3)
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: DiskUsage(free, 0, free))
    try:
        assert backup.local_capacity(case.plan).is_dir()
        assert free > backup.RUN_BUDGET
        assert case.plan.max_spool_bytes > backup.RUN_BUDGET
    finally:
        for descriptor in case.fds:
            os.close(descriptor)
