"""Root-host reattestation of one unchanged, accepted, running AI deployment.

CLI: --anchor ROOT_PROTECTED_JSON. Never creates anchors, starts containers,
executes inside them, accesses DB/auth/env, changes policy or reruns model proof.
Parent alone seeds the anchor after actual acceptance and controls the timer.

Closed anchor keys: schema_version=1, receipt_path, audit_path, docker_binary,
docker_binary_sha256, docker_config_directory, docker_socket,
initial_receipt_sha256, immutable_receipt_sha256, original_proof_issued_at,
facts_sha256, spec. spec keys: container_id, image_id, init_pid, worker_pid,
cli_path, workspace_path, apparmor_directory, companions (CID->image digest),
network_ids, policy_paths. Policy paths contain PUBLIC frozen policy only, under
/etc/peerly-ai/policies; never place credentials/config-env in that directory.
facts_sha256 is sha(canonical(HostProbe(anchor, deadline).facts(accepted_receipt))),
seeded by parent from the accepted deployment, not an anchor-creation CLI capability.
immutable_receipt_sha256 hashes canonical receipt JSON excluding ONLY issued_at
and expires_at; initial_receipt_sha256 hashes the exact original receipt bytes.
Root trusted control is an explicit assumption, not malicious-root hardening.
Root installs/reads this helper without mutable parent imports or inherited Python
configuration (python3 -I /root/protected/renew_ai_receipt.py --anchor ...).
The parent must verify the anchored init/worker are the actual accepted processes;
this tool cannot establish initial provider/model/account acceptance.
No timer is installed; any scheduling/activation is a separate parent operation.

Loaded AppArmor identity/hash is checked. Seccomp source + SecurityOpt + same
process are reaffirmed; this does NOT claim to read loaded BPF. Gateway same
image/process/read-only root/public policy, network/endpoint identity and trusted
root policy control support unchanged-egress attestation, not a new network test.
PREPARED audit precedes rename; COMMITTED follows. These are not one atomic
filesystem transaction. An unresolved/partial record blocks all later attempts
until parent manually reconciles it. Audit caps fail, never truncate history.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Never
from uuid import UUID, uuid4

MAX_JSON = 32768
MAX_RECEIPT = 16384
MAX_OUTPUT = 131072
MAX_AUDIT = 8 * 1024 * 1024
MAX_AUDIT_LINE = 4096
MAX_BINARY = 512 * 1024 * 1024
MAX_POLICY = 131072
MIN_REMAINING = timedelta(minutes=10)
LIFETIME = timedelta(hours=23)
OPERATION_SECONDS = 10
COMMAND_SECONDS = 3
ROOT_UID = 0
AI_UID = 10002
MIN_PROCESSES = 32
MAX_PROCESSES = 40
MAX_COMPANIONS = 4
MAX_VERSION = 100
ASCII_CONTROL = 32
AUDIT_PAIR = 2
MAX_PROFILES = 4096
APPARMOR_HASH_MODE = 0o444
APPARMOR_POLICY = Path("/sys/kernel/security/apparmor/policy")
NAMESPACES = ("mnt", "pid", "net", "user", "ipc", "uts", "cgroup")
PROOFS = frozenset(
    {
        "tool_auth_denial",
        "namespace_denial",
        "native_resource_fit",
        "transport_egress",
        "credential_refresh",
        "text_image_schema",
        "same_owner_binding",
    }
)
ANCHOR_KEYS = frozenset(
    {
        "schema_version",
        "receipt_path",
        "audit_path",
        "docker_binary",
        "docker_binary_sha256",
        "docker_config_directory",
        "docker_socket",
        "initial_receipt_sha256",
        "immutable_receipt_sha256",
        "original_proof_issued_at",
        "facts_sha256",
        "spec",
    }
)
SPEC_KEYS = frozenset(
    {
        "container_id",
        "image_id",
        "init_pid",
        "worker_pid",
        "cli_path",
        "workspace_path",
        "apparmor_directory",
        "companions",
        "network_ids",
        "policy_paths",
    }
)
RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "stage",
        "model",
        "account_binding_sha256",
        "prompt_version",
        "result_schema_version",
        "adapter_version",
        "deployment_id",
        "issued_at",
        "expires_at",
        "binary_sha256",
        "policy_sha256",
        "boot_id",
        "network_namespace",
        "pid_namespace",
        "cgroup_membership",
        "memory_max",
        "pids_max",
        "cpu_max",
        "workspace_bytes",
        "evidence",
    }
)
CONTAINER_FORMAT = (
    '{"Id":{{json .Id}},"Image":{{json .Image}},'
    '"Running":{{json .State.Running}},"Paused":{{json .State.Paused}},'
    '"Restarting":{{json .State.Restarting}},"Pid":{{json .State.Pid}},'
    '"StartedAt":{{json .State.StartedAt}},"User":{{json .Config.User}},'
    '"ReadonlyRootfs":{{json .HostConfig.ReadonlyRootfs}},'
    '"SecurityOpt":{{json .HostConfig.SecurityOpt}},"Mounts":{{json .Mounts}}}'
)
NETWORK_FORMAT = (
    '{"Id":{{json .Id}},"Internal":{{json .Internal}},"Containers":{{json .Containers}}}'
)

type Json = str | int | float | bool | list[Json] | dict[str, Json] | None


class RenewalError(Exception):
    """Fixed code only; OS/provider exception text is never an output contract."""


def reject() -> Never:
    raise RenewalError("attestation_rejected")


def checked(value: object) -> Json:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, list):
        return [checked(item) for item in value]
    if isinstance(value, dict):
        return {string(key): checked(item) for key, item in value.items()}
    reject()


def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            reject()
        result[key] = value
    return result


def parse(data: bytes, limit: int = MAX_JSON) -> dict[str, Json]:
    if not 0 < len(data) <= limit:
        reject()
    value: object = json.loads(
        data, object_pairs_hook=unique, parse_constant=lambda _value: reject()
    )
    return obj(checked(value))


def obj(value: object) -> dict[str, Json]:
    if not isinstance(value, dict):
        reject()
    return {string(key): checked(item) for key, item in value.items()}


def string(value: object) -> str:
    if not isinstance(value, str) or not value or any(ord(item) < ASCII_CONTROL for item in value):
        reject()
    return value


def integer(value: object) -> int:
    if type(value) is not int or not 0 < value < (1 << 63):
        reject()
    return value


def digest(value: object) -> str:
    result = string(value)
    if re.fullmatch(r"[0-9a-f]{64}", result) is None:
        reject()
    return result


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc(value: object) -> datetime:
    at = datetime.fromisoformat(string(value).replace("Z", "+00:00"))
    if at.tzinfo is None:
        reject()
    return at.astimezone(UTC)


def absolute(value: object) -> Path:
    path = Path(string(value))
    if not path.is_absolute() or ".." in path.parts or path == Path("/"):
        reject()
    return path


@dataclass(frozen=True, slots=True)
class Anchor:
    value: dict[str, Json]
    encoded_sha: str

    @classmethod
    def decode(cls, encoded: bytes) -> "Anchor":
        value = parse(encoded)
        if set(value) != ANCHOR_KEYS or integer(value["schema_version"]) != 1:
            reject()
        spec = obj(value["spec"])
        if set(spec) != SPEC_KEYS:
            reject()
        for key in (
            "docker_binary_sha256",
            "initial_receipt_sha256",
            "immutable_receipt_sha256",
            "facts_sha256",
        ):
            digest(value[key])
        for key in (
            "receipt_path",
            "audit_path",
            "docker_binary",
            "docker_config_directory",
            "docker_socket",
        ):
            absolute(value[key])
        if value["receipt_path"] == value["audit_path"]:
            reject()
        utc(value["original_proof_issued_at"])
        identifier(spec["container_id"])
        image(spec["image_id"])
        for key in ("init_pid", "worker_pid"):
            integer(spec[key])
        for key in ("cli_path", "workspace_path"):
            absolute(spec[key])
        directory = absolute(spec["apparmor_directory"])
        if (
            re.fullmatch(
                r"/sys/kernel/security/apparmor/policy/profiles/peerly-ai-worker-v1\.[0-9]+",
                str(directory),
            )
            is None
        ):
            reject()
        source_spec(spec)
        return cls(value, sha(encoded))

    @property
    def spec(self) -> dict[str, Json]:
        return obj(self.value["spec"])


def source_spec(spec: dict[str, Json]) -> None:
    companions = obj(spec["companions"])
    if not 1 <= len(companions) <= MAX_COMPANIONS:
        reject()
    for cid, identity in companions.items():
        identifier(cid)
        image(identity)
    for network in sequence(spec["network_ids"], 16):
        identifier(network)
    for path in sequence(spec["policy_paths"], 8):
        if not absolute(path).is_relative_to("/etc/peerly-ai/policies"):
            reject()


def identifier(value: object) -> str:
    return digest(value)


def image(value: object) -> str:
    result = string(value)
    if not result.startswith("sha256:"):
        reject()
    digest(result.removeprefix("sha256:"))
    return result


def sequence(value: object, maximum: int) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        reject()
    result = [string(item) for item in value]
    if len(set(result)) != len(result):
        reject()
    return result


@contextmanager
def parent(path: Path) -> Iterator[int]:
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if info.st_uid != ROOT_UID or info.st_mode & 0o022:
                reject()
        yield descriptor
    finally:
        os.close(descriptor)


def metadata(fd: int, limit: int) -> os.stat_result:
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != ROOT_UID
        or info.st_mode & 0o7022
        or not 0 <= info.st_size <= limit
    ):
        reject()
    return info


def bounded(fd: int, limit: int) -> bytes:
    data = bytearray()
    while len(data) <= limit:
        chunk = os.read(fd, min(65536, limit + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
    if len(data) > limit:
        reject()
    return bytes(data)


def protected(path: Path, limit: int) -> tuple[bytes, os.stat_result]:
    with parent(path) as directory:
        fd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory
        )
        try:
            before = metadata(fd, limit)
            data = bounded(fd, limit)
            after = metadata(fd, limit)
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                reject()
            return data, before
        finally:
            os.close(fd)


def kernel(path: Path, limit: int = MAX_OUTPUT) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        return bounded(fd, limit)
    finally:
        os.close(fd)


def apparmor_link(path: Path, pattern: str) -> tuple[os.stat_result, str]:
    info = path.lstat()
    if not stat.S_ISLNK(info.st_mode) or info.st_uid != ROOT_UID:
        reject()
    target = os.readlink(path)
    if re.fullmatch(pattern, target) is None:
        reject()
    return info, target


def apparmor_target(target: str) -> Path:
    if re.fullmatch(r"\.\./\.\./raw_data/[0-9]+/sha256", target) is None:
        reject()
    revision = target.split("/")[-2]
    raw = APPARMOR_POLICY / "raw_data"
    for directory in (raw, raw / revision):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != ROOT_UID or info.st_mode & 0o022:
            reject()
    return raw / revision / "sha256"


def apparmor_hash(directory: Path) -> str:
    """Only this known kernel export follows its two validated AppArmor links.

    Linux AppArmor's policy link is a kernel magic link, not a filesystem path
    that Path.resolve can reconstruct. raw_sha256 is its finite relative link
    into the loaded raw-data revision. No arbitrary symlink reader is exposed.
    """
    if (
        directory.parent != APPARMOR_POLICY / "profiles"
        or re.fullmatch(r"peerly-ai-worker-v1\.[0-9]+", directory.name) is None
    ):
        reject()
    leaf = directory / "raw_sha256"
    policy_pattern = r"apparmorfs:\[[0-9]+\]"
    raw_pattern = r"\.\./\.\./raw_data/[0-9]+/sha256"
    policy_before = apparmor_link(APPARMOR_POLICY, policy_pattern)
    leaf_before = apparmor_link(leaf, raw_pattern)
    target = apparmor_target(leaf_before[1])
    expected = target.lstat()
    fd = os.open(leaf, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != ROOT_UID
            or stat.S_IMODE(before.st_mode) != APPARMOR_HASH_MODE
            or not same_file(before, expected)
        ):
            reject()
        result = digest(bounded(fd, 128).decode().strip())
        if not same_file(before, os.fstat(fd)):
            reject()
    finally:
        os.close(fd)
    if not same_file(expected, target.lstat()):
        reject()
    for path, pattern, expected_link in (
        (APPARMOR_POLICY, policy_pattern, policy_before),
        (leaf, raw_pattern, leaf_before),
    ):
        current = apparmor_link(path, pattern)
        if current[1] != expected_link[1] or not same_file(current[0], expected_link[0]):
            reject()
    return result


def file_hash(path: Path, deadline: float, limit: int = MAX_BINARY) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            reject()
        result = hashlib.sha256()
        total = 0
        while chunk := os.read(fd, 65536):
            total += len(chunk)
            if time.monotonic() >= deadline or total > limit:
                reject()
            result.update(chunk)
        after = os.fstat(fd)
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            reject()
        return result.hexdigest()
    finally:
        os.close(fd)


def command(argv: tuple[str, ...], deadline: float) -> bytes:
    output = bytearray()
    errors = 0
    end = min(deadline, time.monotonic() + COMMAND_SECONDS)
    process = subprocess.Popen(  # noqa: S603 - fixed Docker binary/inspect argv, root-protected anchor.
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8"},
        close_fds=True,
        start_new_session=True,
    )
    try:
        if process.stdout is None or process.stderr is None:
            reject()
        with selectors.DefaultSelector() as poll:
            poll.register(process.stdout, selectors.EVENT_READ)
            poll.register(process.stderr, selectors.EVENT_READ)
            while poll.get_map():
                remaining = end - time.monotonic()
                if remaining <= 0:
                    reject()
                for key, _mask in poll.select(remaining):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        poll.unregister(key.fd)
                    elif key.fileobj is process.stdout:
                        output.extend(chunk)
                    else:
                        errors += len(chunk)
                    if len(output) > MAX_OUTPUT or errors > MAX_OUTPUT:
                        reject()
        if process.wait(timeout=max(0.001, end - time.monotonic())) != 0:
            reject()
        return bytes(output)
    finally:
        close_command(process)


def close_command(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=1)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()


def receipt(value: dict[str, Json], anchor: Anchor, now: datetime) -> None:
    if (
        set(value) != RECEIPT_KEYS
        or integer(value["schema_version"]) != 1
        or value["stage"] != "provider_accepted"
    ):
        reject()
    issued, expires = utc(value["issued_at"]), utc(value["expires_at"])
    if (
        not issued <= now
        or expires - now < MIN_REMAINING
        or not timedelta(0) < expires - issued <= timedelta(days=1)
    ):
        reject()
    if utc(anchor.value["original_proof_issued_at"]) > issued:
        reject()
    stable = {key: item for key, item in value.items() if key not in {"issued_at", "expires_at"}}
    if sha(canonical(stable)) != anchor.value["immutable_receipt_sha256"]:
        reject()
    receipt_shape(value)


def receipt_shape(value: dict[str, Json]) -> None:
    if set(obj(value["evidence"])) != PROOFS:
        reject()
    for proof in obj(value["evidence"]).values():
        digest(proof)
    for key in ("binary_sha256", "policy_sha256", "account_binding_sha256"):
        digest(value[key])
    UUID(string(value["deployment_id"]))
    UUID(string(value["boot_id"]))
    if not MIN_PROCESSES <= integer(value["pids_max"]) <= MAX_PROCESSES:
        reject()
    if (
        integer(value["memory_max"]) > 2 * 1024**3
        or integer(value["workspace_bytes"]) > 64 * 1024**2
    ):
        reject()
    for key in ("model", "prompt_version", "result_schema_version", "adapter_version"):
        if len(string(value[key])) > MAX_VERSION:
            reject()
    for key, pattern in (
        ("network_namespace", r"net:\[[0-9]+\]"),
        ("pid_namespace", r"pid:\[[0-9]+\]"),
        ("cpu_max", r"[0-9]+ [0-9]+"),
    ):
        if re.fullmatch(pattern, string(value[key])) is None:
            reject()


def normalized_mounts(value: object) -> list[Json]:
    """Docker Mounts is a set; retain every binding field, normalize only order."""
    if not isinstance(value, list):
        reject()
    mounts: dict[str, Json] = {}
    for item in value:
        mount = obj(item)
        destination = str(absolute(mount.get("Destination")))
        if destination in mounts:
            reject()
        mounts[destination] = mount
    return [mounts[destination] for destination in sorted(mounts)]


@dataclass(slots=True)
class HostProbe:
    anchor: Anchor
    deadline: float

    def docker(self, kind: str, identity: str) -> dict[str, Json]:
        value = self.anchor.value
        config = absolute(value["docker_config_directory"])
        with parent(config / "unused") as fd, os.scandir(fd) as entries:
            if next(entries, None) is not None:
                reject()
        if (
            file_hash(absolute(value["docker_binary"]), self.deadline)
            != value["docker_binary_sha256"]
        ):
            reject()
        if kind not in {"container", "network"}:
            reject()
        identifier(identity)
        fmt = CONTAINER_FORMAT if kind == "container" else NETWORK_FORMAT
        result = parse(
            command(
                (
                    string(value["docker_binary"]),
                    "--config",
                    str(config),
                    "--host",
                    "unix://" + string(value["docker_socket"]),
                    kind,
                    "inspect",
                    identity,
                    "--format",
                    fmt,
                ),
                self.deadline,
            ),
            MAX_OUTPUT,
        )
        if kind == "container":
            result["Mounts"] = normalized_mounts(result["Mounts"])
        return result

    def process(self, pid: int) -> dict[str, Json]:
        base = Path(f"/proc/{pid}")
        raw = kernel(base / "stat").decode()
        parts = raw.rsplit(")", 1)[1].split()
        if parts[0] in {"Z", "X", "T", "t"}:
            reject()
        status = dict(
            line.split(":", 1)
            for line in kernel(base / "status").decode().splitlines()
            if ":" in line
        )
        if any(
            [int(item) for item in status[key].split()] != [AI_UID] * 4 for key in ("Uid", "Gid")
        ):
            reject()
        if status["NoNewPrivs"].strip() != "1" or status["Seccomp"].strip() != "2":
            reject()
        if any(
            int(status[key], 16) != 0 for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
        ):
            reject()
        result: dict[str, Json] = {
            "pid": pid,
            "start_ticks": parts[19],
            "ppid": parts[1],
            "status": {
                key: status[key].strip()
                for key in ("Uid", "Gid", "NoNewPrivs", "Seccomp", "Seccomp_filters")
            },
            "namespaces": {name: os.readlink(base / "ns" / name) for name in NAMESPACES},
            "cgroup": kernel(base / "cgroup").decode().strip(),
            "mounts_sha256": sha(kernel(base / "mountinfo")),
            "rlimits_sha256": sha(kernel(base / "limits")),
            "apparmor": kernel(base / "attr/current").decode().strip(),
        }
        if result["apparmor"] != "peerly-ai-worker-v1 (enforce)":
            reject()
        result["executable"] = os.readlink(base / "exe")
        return result

    def facts(self, current: dict[str, Json]) -> dict[str, Json]:
        spec = self.anchor.spec
        cid = identifier(spec["container_id"])
        container = self.docker("container", cid)
        if (
            container["Id"] != cid
            or container["Image"] != spec["image_id"]
            or container["Running"] is not True
            or container["Paused"] is not False
            or container["Restarting"] is not False
            or container["Pid"] != spec["init_pid"]
            or container["ReadonlyRootfs"] is not True
            or container["User"] not in {"10002", "10002:10002"}
        ):
            reject()
        init_pid, worker_pid = integer(spec["init_pid"]), integer(spec["worker_pid"])
        init, worker = self.process(init_pid), self.process(worker_pid)
        if worker_pid != init_pid and worker["ppid"] != str(init_pid):
            reject()
        if init["namespaces"] != worker["namespaces"] or init["cgroup"] != worker["cgroup"]:
            reject()
        namespaces = obj(init["namespaces"])
        if (
            current["network_namespace"] != namespaces["net"]
            or current["pid_namespace"] != namespaces["pid"]
        ):
            reject()
        if string(current["cgroup_membership"]) != "0::/":
            reject()
        boot = kernel(Path("/proc/sys/kernel/random/boot_id"), 128).decode().strip()
        if boot != current["boot_id"]:
            reject()
        root = Path(f"/proc/{init_pid}/root")
        limits = {
            name: kernel(root / "sys/fs/cgroup" / name, 4096).decode().strip()
            for name in ("pids.max", "memory.max", "cpu.max", "cgroup.procs", "cgroup.freeze")
        }
        if (
            limits["pids.max"] != str(current["pids_max"])
            or limits["memory.max"] != str(current["memory_max"])
            or limits["cpu.max"] != current["cpu_max"]
            or limits["cgroup.freeze"] != "0"
        ):
            reject()
        members = limits.pop("cgroup.procs").split()
        if str(init_pid) not in members or str(worker_pid) not in members:
            reject()
        volume = os.statvfs(root / absolute(spec["workspace_path"]).relative_to("/"))
        if not volume.f_flag & os.ST_NOEXEC or volume.f_blocks * volume.f_frsize > integer(
            current["workspace_bytes"]
        ):
            reject()
        if not os.statvfs(root).f_flag & os.ST_RDONLY:
            reject()
        binary = file_hash(root / absolute(spec["cli_path"]).relative_to("/"), self.deadline)
        if binary != current["binary_sha256"]:
            reject()
        result: dict[str, Json] = {
            "container": container,
            "init": init,
            "worker": worker,
            "boot": boot,
            "limits": {key: checked(value) for key, value in limits.items()},
            "binary_sha256": binary,
            "workspace_bytes": volume.f_blocks * volume.f_frsize,
            "apparmor": self.apparmor(),
            "networks": self.networks(),
            "companions": self.companions(),
            "public_policy": {
                path: file_hash(absolute(path), self.deadline, MAX_POLICY)
                for path in sequence(spec["policy_paths"], 8)
            },
        }
        if time.monotonic() >= self.deadline:
            reject()
        return result

    def apparmor(self) -> dict[str, Json]:
        directory = absolute(self.anchor.spec["apparmor_directory"])
        matches: list[str] = []
        with os.scandir(directory.parent) as entries:
            for count, entry in enumerate(entries):
                if count >= MAX_PROFILES or time.monotonic() >= self.deadline:
                    reject()
                if entry.name.startswith("peerly-ai-worker-v1."):
                    matches.append(entry.name)
        if matches != [directory.name]:
            reject()
        name = kernel(directory / "name", 256).decode().strip()
        mode = kernel(directory / "mode", 128).decode().strip()
        raw_hash = apparmor_hash(directory)
        if name != "peerly-ai-worker-v1" or mode != "enforce":
            reject()
        return {"directory": str(directory), "name": name, "mode": mode, "raw_sha256": raw_hash}

    def networks(self) -> dict[str, Json]:
        result: dict[str, Json] = {}
        for identity in sequence(self.anchor.spec["network_ids"], 16):
            value = self.docker("network", identity)
            if value["Id"] != identity or type(value["Internal"]) is not bool:
                reject()
            obj(value["Containers"])
            result[identity] = value
        return result

    def companions(self) -> dict[str, Json]:
        result: dict[str, Json] = {}
        for cid, expected_image in obj(self.anchor.spec["companions"]).items():
            value = self.docker("container", cid)
            if (
                value["Id"] != cid
                or value["Image"] != expected_image
                or value["Running"] is not True
                or value["Paused"] is not False
                or value["Restarting"] is not False
                or value["ReadonlyRootfs"] is not True
            ):
                reject()
            pid = integer(value["Pid"])
            parts = kernel(Path(f"/proc/{pid}/stat")).decode().rsplit(")", 1)[1].split()
            if parts[0] in {"Z", "X", "T", "t"}:
                reject()
            result[cid] = {"container": value, "start_ticks": parts[19]}
        return result


@dataclass(frozen=True, slots=True)
class RenewalPlan:
    encoded: bytes
    intent: dict[str, Json]


def plan(anchor: Anchor, encoded: bytes, now: datetime) -> RenewalPlan:
    current = parse(encoded, MAX_RECEIPT)
    receipt(current, anchor, now)
    replacement = dict(current, issued_at=now.isoformat(), expires_at=(now + LIFETIME).isoformat())
    updated = canonical(replacement) + b"\n"
    intent: dict[str, Json] = {
        "schema_version": 1,
        "operation": str(uuid4()),
        "anchor_sha256": anchor.encoded_sha,
        "container_id": anchor.spec["container_id"],
        "deployment_id": current["deployment_id"],
        "original_proof_issued_at": anchor.value["original_proof_issued_at"],
        "evidence_sha256": sha(canonical(current["evidence"])),
        "old_sha256": sha(encoded),
        "new_sha256": sha(updated),
        "old_issued_at": current["issued_at"],
        "old_expires_at": current["expires_at"],
        "new_issued_at": replacement["issued_at"],
        "new_expires_at": replacement["expires_at"],
    }
    return RenewalPlan(updated, intent)


@contextmanager
def locked(path: Path) -> Iterator[None]:
    with parent(path) as directory:
        fd = os.open(
            path.name,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            0o600,
            dir_fd=directory,
        )
        try:
            if metadata(fd, 0).st_mode & 0o077:
                reject()
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)


@dataclass(slots=True)
class Journal:
    fd: int

    def previous(self, anchor: Anchor, encoded: bytes) -> None:
        info = metadata(self.fd, MAX_AUDIT)
        if info.st_mode & 0o077:
            reject()
        if info.st_size == 0:
            if sha(encoded) != anchor.value["initial_receipt_sha256"]:
                reject()
            if parse(encoded)["issued_at"] != anchor.value["original_proof_issued_at"]:
                reject()
            return
        os.lseek(self.fd, max(0, info.st_size - MAX_AUDIT_LINE * 3), os.SEEK_SET)
        tail = bounded(self.fd, MAX_AUDIT_LINE * 3)
        if not tail.endswith(b"\n"):
            reject()
        lines = tail.splitlines()
        if len(lines) < AUDIT_PAIR:
            reject()
        prepared, committed = (parse(line, MAX_AUDIT_LINE) for line in lines[-2:])
        if prepared.pop("state", None) != "PREPARED" or committed.pop("state", None) != "COMMITTED":
            reject()
        if (
            prepared != committed
            or committed.get("anchor_sha256") != anchor.encoded_sha
            or committed.get("new_sha256") != sha(encoded)
        ):
            reject()

    def reserve(self, intent: dict[str, Json]) -> None:
        prepared, committed = (self.line(intent, state) for state in ("PREPARED", "COMMITTED"))
        if metadata(self.fd, MAX_AUDIT).st_size + len(prepared) + len(committed) > MAX_AUDIT:
            reject()

    @staticmethod
    def line(intent: dict[str, Json], state: str) -> bytes:
        encoded = canonical(dict(intent, state=state)) + b"\n"
        if len(encoded) > MAX_AUDIT_LINE:
            reject()
        return encoded

    def append(self, intent: dict[str, Json], state: str) -> None:
        encoded = self.line(intent, state)
        if metadata(self.fd, MAX_AUDIT).st_size + len(encoded) > MAX_AUDIT:
            reject()
        # A short write is deliberately NOT retried: partial audit blocks reconciliation.
        if os.write(self.fd, encoded) != len(encoded):
            reject()
        os.fsync(self.fd)


@contextmanager
def journal(path: Path) -> Iterator[Journal]:
    with parent(path) as directory:
        fd = os.open(
            path.name,
            os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            0o600,
            dir_fd=directory,
        )
        try:
            metadata(fd, MAX_AUDIT)
            os.fsync(directory)
            yield Journal(fd)
        finally:
            os.close(fd)


def same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino, left.st_size, left.st_mtime_ns, left.st_ctime_ns) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def verify(anchor: Anchor, encoded: bytes, deadline: float) -> None:
    current = parse(encoded, MAX_RECEIPT)
    receipt(current, anchor, datetime.now(UTC))
    facts = HostProbe(anchor, deadline).facts(current)
    if sha(canonical(facts)) != anchor.value["facts_sha256"] or time.monotonic() >= deadline:
        reject()


def install(
    anchor: Anchor, original: bytes, update: RenewalPlan, audit: Journal, deadline: float
) -> None:
    path = absolute(anchor.value["receipt_path"])
    with parent(path) as directory:
        temporary = ".renew-" + str(uuid4())
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=directory,
        )
        try:
            encoded, info = protected(path, MAX_RECEIPT)
            if encoded != original:
                reject()
            os.fchown(fd, info.st_uid, info.st_gid)
            os.fchmod(fd, stat.S_IMODE(info.st_mode))
            if os.write(fd, update.encoded) != len(update.encoded):
                reject()
            os.fsync(fd)
            receipt(parse(original), anchor, datetime.now(UTC))
            if time.monotonic() >= deadline:
                reject()
            audit.reserve(update.intent)
            audit.append(update.intent, "PREPARED")
            # Audit and receipt are intentionally distinct durable steps. Any error from
            # this point requires manual reconciliation, even if rename did not happen.
            actual, current = protected(path, MAX_RECEIPT)
            if actual != original or not same_file(info, current):
                reject()
            receipt(parse(original), anchor, datetime.now(UTC))
            if time.monotonic() >= deadline:
                reject()
            os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
            audit.append(update.intent, "COMMITTED")
        finally:
            os.close(fd)
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=directory)


def renew(anchor_path: Path) -> dict[str, Json]:
    if os.geteuid() != 0:
        reject()
    deadline = time.monotonic() + OPERATION_SECONDS
    anchor_bytes, info = protected(anchor_path, MAX_JSON)
    if info.st_mode & 0o077:
        reject()
    anchor = Anchor.decode(anchor_bytes)
    path = absolute(anchor.value["receipt_path"])
    if anchor_path in {path, absolute(anchor.value["audit_path"])}:
        reject()
    with (
        locked(anchor_path.with_name(anchor_path.name + ".renew.lock")),
        journal(absolute(anchor.value["audit_path"])) as audit,
    ):
        encoded, _info = protected(path, MAX_RECEIPT)
        audit.previous(anchor, encoded)
        verify(anchor, encoded, deadline)
        verify(anchor, encoded, deadline)
        # Reaffirm the root trust anchor itself before preparing any write.
        if protected(anchor_path, MAX_JSON)[0] != anchor_bytes:
            reject()
        update = plan(anchor, encoded, datetime.now(UTC))
        if time.monotonic() >= deadline:
            reject()
        install(anchor, encoded, update, audit, deadline)
    return {
        "status": "renewed",
        "receipt_sha256": sha(update.encoded),
        "original_proof_issued_at": anchor.value["original_proof_issued_at"],
        "expires_at": update.intent["new_expires_at"],
    }


class ClosedArguments(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RenewalError("invalid_arguments")


def main() -> int:
    parser = ClosedArguments(description=__doc__)
    parser.add_argument("--anchor", required=True)
    try:
        options = parser.parse_args()
        result = renew(absolute(options.anchor))
    except (
        RenewalError,
        OSError,
        ValueError,
        KeyError,
        IndexError,
        subprocess.SubprocessError,
        RecursionError,
    ):
        sys.stdout.write('{"status":"rejected","code":"renewal_not_committed_or_uncertain"}\n')
        return 1
    sys.stdout.write(canonical(result).decode() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
