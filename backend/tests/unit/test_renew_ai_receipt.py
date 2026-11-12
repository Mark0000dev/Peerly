"""Synthetic host facts and task-owned files; no Docker, kernel policy or provider calls."""

import json
import os
import stat
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from deployment.backend import renew_ai_receipt as renewal

READABLE_RECEIPT_MODE = 0o640
TWO_RENEWAL_RECORDS = 4
HASH = "a" * 64
CID = "b" * 64
NETWORK = "c" * 64
IMAGE = "sha256:" + "d" * 64


@dataclass(frozen=True)
class Files:
    anchor: renewal.Anchor
    path: Path
    encoded: bytes
    now: datetime


@pytest.fixture
def files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Files:
    # Emulate a trusted root-owned temporary directory without acquiring host authority.
    @contextmanager
    def local_parent(path: Path) -> Iterator[int]:
        assert path.parent == tmp_path
        descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            yield descriptor
        finally:
            os.close(descriptor)

    monkeypatch.setattr(renewal, "parent", local_parent)
    monkeypatch.setattr(renewal, "ROOT_UID", os.getuid())
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    now = datetime.now(UTC)
    value: dict[str, renewal.Json] = {
        "schema_version": 1,
        "stage": "provider_accepted",
        "model": "synthetic-model",
        "account_binding_sha256": HASH,
        "prompt_version": "1",
        "result_schema_version": "1",
        "adapter_version": "1",
        "deployment_id": "00000000-0000-0000-0000-000000000001",
        "issued_at": (now - timedelta(hours=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "binary_sha256": HASH,
        "policy_sha256": HASH,
        "boot_id": "00000000-0000-0000-0000-000000000002",
        "network_namespace": "net:[1]",
        "pid_namespace": "pid:[2]",
        "cgroup_membership": "0::/",
        "memory_max": 1073741824,
        "pids_max": 32,
        "cpu_max": "50000 100000",
        "workspace_bytes": 67108864,
        "evidence": dict.fromkeys(renewal.PROOFS, HASH),
    }
    encoded = renewal.canonical(value)
    path = tmp_path / "anchor.json"
    spec: dict[str, renewal.Json] = {
        "container_id": CID,
        "image_id": IMAGE,
        "init_pid": 100,
        "worker_pid": 101,
        "cli_path": "/usr/local/lib/peerly-codex/vendor/bin/codex",
        "workspace_path": "/var/lib/peerly-ai/jobs",
        "apparmor_directory": (
            "/sys/kernel/security/apparmor/policy/profiles/peerly-ai-worker-v1.118"
        ),
        "companions": {"e" * 64: IMAGE},
        "network_ids": [NETWORK],
        "policy_paths": ["/etc/peerly-ai/policies/seccomp.json"],
    }
    anchor_value: dict[str, renewal.Json] = {
        "schema_version": 1,
        "receipt_path": str(tmp_path / "receipt.json"),
        "audit_path": str(tmp_path / "audit.jsonl"),
        "docker_binary": "/usr/bin/docker",
        "docker_binary_sha256": HASH,
        "docker_config_directory": "/etc/peerly-ai/empty-docker",
        "docker_socket": "/var/run/docker.sock",
        "initial_receipt_sha256": renewal.sha(encoded),
        "immutable_receipt_sha256": renewal.sha(
            renewal.canonical(
                {key: item for key, item in value.items() if key not in {"issued_at", "expires_at"}}
            )
        ),
        "original_proof_issued_at": value["issued_at"],
        "facts_sha256": renewal.sha(renewal.canonical({"unchanged": True})),
        "spec": spec,
    }
    path.write_bytes(renewal.canonical(anchor_value))
    path.chmod(0o600)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_bytes(encoded)
    receipt_path.chmod(0o640)
    return Files(renewal.Anchor.decode(path.read_bytes()), path, encoded, now)


def source(files: Files) -> dict[str, renewal.Json]:
    return renewal.parse(files.encoded)


def test_only_dates_change_and_original_proof_is_not_relabelled(files: Files) -> None:
    update = renewal.plan(files.anchor, files.encoded, files.now)
    current, updated = source(files), renewal.parse(update.encoded)
    assert renewal.utc(updated.pop("issued_at")) == files.now
    assert renewal.utc(updated.pop("expires_at")) == files.now + timedelta(hours=23)
    current.pop("issued_at")
    current.pop("expires_at")
    assert updated == current
    assert (
        update.intent["original_proof_issued_at"] == files.anchor.value["original_proof_issued_at"]
    )
    assert update.intent["evidence_sha256"] == renewal.sha(renewal.canonical(current["evidence"]))


@pytest.mark.parametrize(
    "change",
    [
        {"stage": "containment"},
        {"model": "other"},
        {"pids_max": 40},
        {"binary_sha256": "f" * 64},
        {"policy_sha256": "f" * 64},
        {"evidence": {}},
        {"network_namespace": "net:[99]"},
        {"extra": True},
        {"schema_version": True},
    ],
)
def test_no_authority_or_immutable_field_can_be_changed(
    files: Files, change: dict[str, renewal.Json]
) -> None:
    with pytest.raises(renewal.RenewalError):
        renewal.plan(files.anchor, renewal.canonical(source(files) | change), files.now)


@pytest.mark.parametrize("remaining", [-60, 0, 599])
def test_expired_or_near_expired_receipt_never_renewed(files: Files, remaining: int) -> None:
    value = source(files)
    value["expires_at"] = (files.now + timedelta(seconds=remaining)).isoformat()
    with pytest.raises(renewal.RenewalError):
        renewal.plan(files.anchor, renewal.canonical(value), files.now)


@pytest.mark.parametrize("encoded", [b'{"x":1,"x":2}', b'{"x":NaN}', b"[]", b"{} " * 9000])
def test_closed_bounded_json(encoded: bytes) -> None:
    with pytest.raises((renewal.RenewalError, ValueError)):
        renewal.parse(encoded)


def test_anchor_closed_paths_and_companion_contract(files: Files) -> None:
    for key, value in (("schema_version", True), ("extra", True), ("docker_binary", "relative")):
        candidate = files.anchor.value | {key: value}
        with pytest.raises(renewal.RenewalError):
            renewal.Anchor.decode(renewal.canonical(candidate))
    spec = files.anchor.spec
    changes: tuple[tuple[str, renewal.Json], ...] = (
        ("policy_paths", ["/var/private/auth.json"]),
        ("companions", {}),
        ("apparmor_directory", "/etc/apparmor.d/source-only"),
    )
    for spec_key, spec_value in changes:
        candidate = files.anchor.value | {"spec": spec | {spec_key: spec_value}}
        with pytest.raises(renewal.RenewalError):
            renewal.Anchor.decode(renewal.canonical(candidate))


def unchanged(self: renewal.HostProbe, current: dict[str, renewal.Json]) -> dict[str, renewal.Json]:
    del self, current
    return {"unchanged": True}


def test_complete_renewal_then_next_renewal_preserves_modes_and_audit(
    files: Files, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(renewal.HostProbe, "facts", unchanged)
    first = renewal.renew(files.path)
    assert first["status"] == "renewed"
    path = renewal.absolute(files.anchor.value["receipt_path"])
    assert stat.S_IMODE(path.stat().st_mode) == READABLE_RECEIPT_MODE
    audit_path = renewal.absolute(files.anchor.value["audit_path"])
    initial = audit_path.read_bytes()
    assert [json.loads(line)["state"] for line in initial.splitlines()] == ["PREPARED", "COMMITTED"]
    renewal.renew(files.path)
    assert audit_path.read_bytes().startswith(initial)
    assert len(audit_path.read_bytes().splitlines()) == TWO_RENEWAL_RECORDS
    assert not list(files.path.parent.glob(".renew-*"))


def test_changed_facts_prevents_any_receipt_or_audit_write(
    files: Files, monkeypatch: pytest.MonkeyPatch
) -> None:
    def changed(
        self: renewal.HostProbe, current: dict[str, renewal.Json]
    ) -> dict[str, renewal.Json]:
        del self, current
        return {"unchanged": False}

    monkeypatch.setattr(renewal.HostProbe, "facts", changed)
    with pytest.raises(renewal.RenewalError):
        renewal.renew(files.path)
    assert renewal.absolute(files.anchor.value["receipt_path"]).read_bytes() == files.encoded
    assert renewal.absolute(files.anchor.value["audit_path"]).read_bytes() == b""


@pytest.mark.parametrize("fault", ["before_rename", "after_rename"])
def test_interrupted_commit_blocks_next_attempt_until_manual_reconciliation(
    files: Files, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    monkeypatch.setattr(renewal.HostProbe, "facts", unchanged)
    original_append = renewal.Journal.append

    def interrupted(self: renewal.Journal, intent: dict[str, renewal.Json], state: str) -> None:
        if state == "COMMITTED":
            raise OSError("synthetic commit failure")
        original_append(self, intent, state)
        if fault == "before_rename":
            raise OSError("synthetic pre-rename failure")

    monkeypatch.setattr(renewal.Journal, "append", interrupted)
    with pytest.raises(OSError, match="synthetic"):
        renewal.renew(files.path)
    path = renewal.absolute(files.anchor.value["receipt_path"])
    assert (path.read_bytes() == files.encoded) == (fault == "before_rename")
    monkeypatch.setattr(renewal.Journal, "append", original_append)
    with pytest.raises(renewal.RenewalError):
        renewal.renew(files.path)
    assert not list(files.path.parent.glob(".renew-*"))


def test_partial_journal_and_capacity_never_truncate_history(files: Files) -> None:
    audit_path = renewal.absolute(files.anchor.value["audit_path"])
    audit_path.write_bytes(b'{"partial":')
    audit_path.chmod(0o600)
    with renewal.journal(audit_path) as audit, pytest.raises(renewal.RenewalError):
        audit.previous(files.anchor, files.encoded)
    assert audit_path.read_bytes() == b'{"partial":'
    audit_path.write_bytes(b"x" * renewal.MAX_AUDIT)
    with renewal.journal(audit_path) as audit, pytest.raises(renewal.RenewalError):
        audit.reserve(renewal.plan(files.anchor, files.encoded, files.now).intent)
    assert audit_path.stat().st_size == renewal.MAX_AUDIT


def test_concurrent_controller_is_rejected(files: Files) -> None:
    path = files.path.with_name("exclusive.lock")
    with renewal.locked(path), pytest.raises(BlockingIOError), renewal.locked(path):
        pytest.fail("second lock acquired")


def test_leaf_symlink_hardlink_fifo_and_writable_receipt_rejected(files: Files) -> None:
    path = renewal.absolute(files.anchor.value["receipt_path"])
    alias = path.with_name("alias")
    alias.symlink_to(path)
    with pytest.raises(OSError, match="Too many levels"):
        renewal.protected(alias, renewal.MAX_RECEIPT)
    alias.unlink()
    os.link(path, alias)
    with pytest.raises(renewal.RenewalError):
        renewal.protected(path, renewal.MAX_RECEIPT)
    alias.unlink()
    os.mkfifo(alias, 0o600)
    with pytest.raises(renewal.RenewalError):
        renewal.protected(alias, renewal.MAX_RECEIPT)
    path.chmod(0o666)
    with pytest.raises(renewal.RenewalError):
        renewal.protected(path, renewal.MAX_RECEIPT)


def test_bounded_command_success_failure_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNTHETIC_PRIVATE", "never-inherited")
    code = "import os,sys;sys.stdout.write(str('SYNTHETIC_PRIVATE' in os.environ))"
    assert renewal.command((sys.executable, "-c", code), time.monotonic() + 2) == b"False"
    with pytest.raises(renewal.RenewalError):
        renewal.command((sys.executable, "-c", "raise SystemExit(1)"), time.monotonic() + 2)


def test_bounded_command_overflow_and_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(renewal.RenewalError):
        renewal.command(
            (sys.executable, "-c", "import os;os.write(1,b'x'*200000)"), time.monotonic() + 2
        )
    monkeypatch.setattr(renewal, "COMMAND_SECONDS", 0.05)
    with pytest.raises(renewal.RenewalError):
        renewal.command((sys.executable, "-c", "import time;time.sleep(2)"), time.monotonic() + 2)


@pytest.mark.parametrize(
    "field",
    [
        "pid",
        "image",
        "apparmor",
        "namespaces",
        "rlimits",
        "gateway",
        "network",
        "seccomp",
        "policy",
    ],
)
def test_any_anchored_identity_or_policy_change_rejects_before_write(
    files: Files, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    initial: dict[str, renewal.Json] = dict.fromkeys(
        (
            "pid",
            "image",
            "apparmor",
            "namespaces",
            "rlimits",
            "gateway",
            "network",
            "seccomp",
            "policy",
        ),
        HASH,
    )
    value = files.anchor.value | {"facts_sha256": renewal.sha(renewal.canonical(initial))}
    files.path.write_bytes(renewal.canonical(value))
    initial[field] = "changed"

    def modified(
        self: renewal.HostProbe, current: dict[str, renewal.Json]
    ) -> dict[str, renewal.Json]:
        del self, current
        return initial

    monkeypatch.setattr(renewal.HostProbe, "facts", modified)
    with pytest.raises(renewal.RenewalError):
        renewal.renew(files.path)
    assert renewal.absolute(files.anchor.value["receipt_path"]).read_bytes() == files.encoded


def test_host_resource_reader_checks_actual_cgroup_without_container_exec(
    files: Files, monkeypatch: pytest.MonkeyPatch
) -> None:
    limits = {
        "pids.max": "32",
        "memory.max": "1073741824",
        "cpu.max": "50000 100000",
        "cgroup.procs": "100\n101",
        "cgroup.freeze": "0",
    }
    current = source(files)

    def kernel(path: Path, limit: int = renewal.MAX_OUTPUT) -> bytes:
        assert limit <= renewal.MAX_OUTPUT
        if path.name == "boot_id":
            return str(current["boot_id"]).encode()
        assert path.parent == Path("/proc/100/root/sys/fs/cgroup")
        return limits[path.name].encode()

    def docker(self: renewal.HostProbe, kind: str, identity: str) -> dict[str, renewal.Json]:
        del self
        assert (kind, identity) == ("container", CID)
        return {
            "Id": CID,
            "Image": IMAGE,
            "Running": True,
            "Paused": False,
            "Restarting": False,
            "Pid": 100,
            "ReadonlyRootfs": True,
            "User": "10002:10002",
        }

    def process(self: renewal.HostProbe, pid: int) -> dict[str, renewal.Json]:
        del self
        assert pid in {100, 101}
        return {
            "ppid": "100",
            "cgroup": "0::/actual-host-cgroup",
            "namespaces": {"net": "net:[1]", "pid": "pid:[2]"},
        }

    def stable(self: renewal.HostProbe) -> dict[str, renewal.Json]:
        del self
        return {"identity": HASH}

    def file_hash(path: Path, deadline: float, limit: int = renewal.MAX_BINARY) -> str:
        assert deadline > time.monotonic()
        assert path == Path("/proc/100/root/usr/local/lib/peerly-codex/vendor/bin/codex") or (
            path == Path("/etc/peerly-ai/policies/seccomp.json") and limit == renewal.MAX_POLICY
        )
        return HASH

    def statvfs(path: Path) -> os.statvfs_result:
        assert path in {Path("/proc/100/root"), Path("/proc/100/root/var/lib/peerly-ai/jobs")}
        return os.statvfs_result(
            (4096, 4096, 16384, 0, 0, 0, 0, 0, os.ST_NOEXEC | os.ST_RDONLY, 255)
        )

    monkeypatch.setattr(renewal, "kernel", kernel)
    monkeypatch.setattr(renewal.HostProbe, "docker", docker)
    monkeypatch.setattr(renewal.HostProbe, "process", process)
    for method in ("apparmor", "networks", "companions"):
        monkeypatch.setattr(renewal.HostProbe, method, stable)
    monkeypatch.setattr(renewal, "file_hash", file_hash)
    monkeypatch.setattr(os, "statvfs", statvfs)
    probe = renewal.HostProbe(files.anchor, time.monotonic() + 5)
    facts = probe.facts(current)
    assert renewal.obj(facts["limits"])["pids.max"] == "32"
    for key, changed in (
        ("pids.max", "40"),
        ("memory.max", "max"),
        ("cpu.max", "max 100000"),
        ("cgroup.procs", "100"),
        ("cgroup.freeze", "1"),
    ):
        previous = limits[key]
        limits[key] = changed
        with pytest.raises(renewal.RenewalError):
            probe.facts(current)
        limits[key] = previous


def test_docker_inspection_contract_never_requests_private_args_or_environment() -> None:
    assert ".Config.Env" not in renewal.CONTAINER_FORMAT
    assert ".Config.Cmd" not in renewal.CONTAINER_FORMAT
    assert ".Args" not in renewal.CONTAINER_FORMAT
    assert "SecurityOpt" in renewal.CONTAINER_FORMAT
    assert "Mounts" in renewal.CONTAINER_FORMAT
    assert "Internal" in renewal.NETWORK_FORMAT
    assert "Containers" in renewal.NETWORK_FORMAT


def test_cli_failure_does_not_print_exception_or_supplied_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["renew_ai_receipt", "--unknown-private-value"])
    assert renewal.main() == 1
    output = capsys.readouterr()
    assert output.err == ""
    assert "private-value" not in output.out
    assert json.loads(output.out)["code"] == "renewal_not_committed_or_uncertain"


def test_process_guard_reads_no_arguments_environment_or_credentials(
    files: Files, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = {
        "Uid": "10002 10002 10002 10002",
        "Gid": "10002 10002 10002 10002",
        "NoNewPrivs": "1",
        "Seccomp": "2",
        "Seccomp_filters": "1",
        "CapInh": "0",
        "CapPrm": "0",
        "CapEff": "0",
        "CapBnd": "0",
        "CapAmb": "0",
    }

    def kernel(path: Path, limit: int = renewal.MAX_OUTPUT) -> bytes:
        assert limit <= renewal.MAX_OUTPUT
        assert path.parent in {Path("/proc/101"), Path("/proc/101/attr")}
        if path.name == "status":
            return "\n".join(f"{key}: {value}" for key, value in values.items()).encode()
        allowed = {
            "stat": "101 (python) S 100 " + "0 " * 30,
            "cgroup": "0::/host-path",
            "mountinfo": "synthetic-mounts",
            "limits": "synthetic-limits",
            "current": "peerly-ai-worker-v1 (enforce)",
        }
        # Any attempted cmdline/environ/auth read fails this synthetic port.
        return allowed[path.name].encode()

    def readlink(path: Path) -> str:
        if path.name == "exe":
            return "/usr/local/bin/python3.12"
        assert path.parent == Path("/proc/101/ns")
        return f"{path.name}:[1]"

    monkeypatch.setattr(renewal, "kernel", kernel)
    monkeypatch.setattr(os, "readlink", readlink)
    probe = renewal.HostProbe(files.anchor, time.monotonic() + 5)
    assert probe.process(101)["rlimits_sha256"] == renewal.sha(b"synthetic-limits")
    for key, bad in (("Uid", "0 0 0 0"), ("NoNewPrivs", "0"), ("Seccomp", "0"), ("CapEff", "1")):
        previous = values[key]
        values[key] = bad
        with pytest.raises(renewal.RenewalError):
            probe.process(101)
        values[key] = previous


@pytest.fixture
def apparmor_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "apparmor"
    tree = root / "tree"
    profile = tree / "profiles" / "peerly-ai-worker-v1.118"
    profile.mkdir(parents=True)
    raw = tree / "raw_data" / "134"
    raw.mkdir(parents=True)
    raw.chmod(0o755)
    raw.parent.chmod(0o755)
    (raw / "sha256").write_text(HASH + "\n")
    (raw / "sha256").chmod(0o444)
    (profile / "raw_sha256").symlink_to("../../raw_data/134/sha256")
    policy = root / "policy"
    policy.symlink_to("tree", target_is_directory=True)
    original = os.readlink

    def magic_readlink(path: str | Path, *, dir_fd: int | None = None) -> str:
        if Path(path) == policy:
            return "apparmorfs:[1236]"
        return original(path, dir_fd=dir_fd)

    # Emulate kernel magic-link lookup: open works, textual resolve does not.
    monkeypatch.setattr(os, "readlink", magic_readlink)
    monkeypatch.setattr(renewal, "APPARMOR_POLICY", policy)
    monkeypatch.setattr(renewal, "ROOT_UID", os.getuid())
    return policy / "profiles" / profile.name


def test_apparmor_magic_link_hash_without_resolve_or_global_nofollow_relaxation(
    apparmor_export: Path,
) -> None:
    with pytest.raises(FileNotFoundError):
        apparmor_export.resolve(strict=True)
    assert renewal.apparmor_hash(apparmor_export) == HASH
    with pytest.raises(OSError, match="Too many levels"):
        renewal.kernel(apparmor_export / "raw_sha256")


@pytest.mark.parametrize(
    "target", ["/etc/shadow", "../../raw_data/not-a-revision/sha256", "../name"]
)
def test_apparmor_export_rejects_any_unapproved_link_target(
    apparmor_export: Path, target: str
) -> None:
    leaf = apparmor_export / "raw_sha256"
    leaf.unlink()
    leaf.symlink_to(target)
    with pytest.raises(renewal.RenewalError):
        renewal.apparmor_hash(apparmor_export)


def test_apparmor_export_rejects_reload_during_hash_read(
    apparmor_export: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = renewal.bounded

    def changed(fd: int, limit: int) -> bytes:
        result = original(fd, limit)
        leaf = apparmor_export / "raw_sha256"
        leaf.unlink()
        leaf.symlink_to("../../raw_data/135/sha256")
        return result

    monkeypatch.setattr(renewal, "bounded", changed)
    with pytest.raises(renewal.RenewalError):
        renewal.apparmor_hash(apparmor_export)


def test_apparmor_export_rejects_writable_or_invalid_hash(apparmor_export: Path) -> None:
    raw = apparmor_export.parent.parent / "raw_data" / "134" / "sha256"
    raw.chmod(0o644)
    with pytest.raises(renewal.RenewalError):
        renewal.apparmor_hash(apparmor_export)
    raw.write_text("not-a-loaded-policy-hash")
    raw.chmod(0o444)
    with pytest.raises(renewal.RenewalError):
        renewal.apparmor_hash(apparmor_export)


def mount_bindings() -> list[renewal.Json]:
    return [
        {
            "Destination": "/var/lib/peerly-ai/credentials",
            "Source": "/synthetic/volume",
            "RW": True,
            "Type": "volume",
            "Driver": "local",
            "Name": "synthetic",
            "Mode": "z",
            "Propagation": "",
        },
        {
            "Destination": "/var/lib/peerly-ai/acceptance",
            "Source": "/synthetic/acceptance",
            "RW": False,
            "Type": "bind",
            "Mode": "",
            "Propagation": "rprivate",
        },
    ]


def test_docker_mount_order_stable_without_dropping_binding_fields() -> None:
    mounts = mount_bindings()
    normalized = renewal.normalized_mounts(mounts)
    assert normalized == renewal.normalized_mounts(list(reversed(mounts)))
    assert normalized == list(reversed(mounts))
    assert renewal.normalized_mounts([]) == []
    with pytest.raises(renewal.RenewalError):
        renewal.normalized_mounts([mounts[0], mounts[0]])


@pytest.mark.parametrize(
    "change",
    [
        {"Source": "/different/source"},
        {"Destination": "/different/target"},
        {"RW": False},
        {"Mode": "different"},
        {"Driver": "other"},
        {"UnexpectedNewField": "not-dropped"},
    ],
)
def test_mount_changes_remain_attestation_changes(change: dict[str, renewal.Json]) -> None:
    original = mount_bindings()
    modified = [renewal.obj(original[0]) | change, original[1]]
    assert renewal.sha(renewal.canonical(renewal.normalized_mounts(original))) != (
        renewal.sha(renewal.canonical(renewal.normalized_mounts(modified)))
    )


def test_host_docker_applies_mount_normalization(
    files: Files, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "empty-config"
    config.mkdir()

    @contextmanager
    def public_directory(path: Path) -> Iterator[int]:
        assert path == config / "unused"
        descriptor = os.open(config, os.O_RDONLY | os.O_DIRECTORY)
        try:
            yield descriptor
        finally:
            os.close(descriptor)

    def binary_hash(path: Path, deadline: float, limit: int = renewal.MAX_BINARY) -> str:
        assert str(path) == files.anchor.value["docker_binary"]
        assert deadline > time.monotonic()
        assert limit == renewal.MAX_BINARY
        return HASH

    orders = iter((mount_bindings(), list(reversed(mount_bindings()))))

    def inspect(argv: tuple[str, ...], deadline: float) -> bytes:
        assert argv[-2:] == ("--format", renewal.CONTAINER_FORMAT)
        assert argv[-5:-2] == ("container", "inspect", CID)
        assert deadline > time.monotonic()
        return renewal.canonical({"Id": CID, "Mounts": next(orders)})

    anchor = renewal.Anchor(files.anchor.value | {"docker_config_directory": str(config)}, HASH)
    monkeypatch.setattr(renewal, "parent", public_directory)
    monkeypatch.setattr(renewal, "file_hash", binary_hash)
    monkeypatch.setattr(renewal, "command", inspect)
    probe = renewal.HostProbe(anchor, time.monotonic() + 5)
    assert probe.docker("container", CID) == probe.docker("container", CID)
