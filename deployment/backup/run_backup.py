"""Parent-activated bounded PG/media backup using existing native rclone crypt."""

import argparse
import asyncio
import configparser
import contextlib
import fcntl
import json
import os
import re
import shutil
import signal
import stat
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from deployment.backup.retention import Retention, VerifiedRun
from deployment.backup.retention import plan as retention_plan
from deployment.restore import capture_backup as capture
from deployment.restore.accept_restore import (
    MAX_DUMP_BYTES,
    MAX_JSON,
    MAX_MEDIA_BYTES,
    MAX_OBJECT_BYTES,
    digest,
    inventory,
    load,
    unique,
)

PRIVATE_DIRECTORY_MODE = 0o700
MAX_CATALOG = 4096
MAX_CATALOG_RECORD = 4096
MAX_QUARANTINED_RUNS = 3
MAX_SPOOL_ENTRIES = 50000
MAX_CREDENTIAL = 65536
MAX_PAYLOAD = MAX_DUMP_BYTES + MAX_MEDIA_BYTES + 2 * MAX_JSON + 1048576
METADATA_RESERVE = 128 * 1024 * 1024
RUN_BUDGET = MAX_PAYLOAD + METADATA_RESERVE
PHASE_SECONDS = 600
RUN_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}")
REFERENCE = re.compile(r"[A-Za-z0-9_.-]{8,128}")
HASH = re.compile(r"[0-9a-f]{64}")
NATIVE_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C",
    "LC_ALL": "C",
    "AWS_EC2_METADATA_DISABLED": "true",
    "GOMEMLIMIT": "160MiB",
}


class BackupError(ValueError):
    """Closed backup rejection; no native stderr or input content is logged."""


@dataclass(frozen=True, slots=True)
class Plan:
    state: Path
    capture_sha256: str
    rclone: Path
    rclone_sha256: str
    key_generation: str
    escrow_drill_reference: str
    max_spool_bytes: int
    retention: Retention


def sealed_input(descriptor: int) -> int:
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) not in {0o400, 0o600}
        or not 0 < info.st_size <= MAX_CREDENTIAL
    ):
        raise BackupError("credential_metadata")
    source = os.pread(descriptor, MAX_CREDENTIAL + 1, 0)
    if len(source) != info.st_size:
        raise BackupError("credential_bound")
    result = os.memfd_create("peerly-backup-input", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        os.fchmod(result, 0o600)
        with os.fdopen(os.dup(result), "wb") as stream:
            stream.write(source)
        os.lseek(result, 0, os.SEEK_SET)
        fcntl.fcntl(
            result,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL,
        )
    except BaseException:
        os.close(result)
        raise
    return result


def read_plan(descriptor: int) -> Plan:
    value: object = json.loads(os.pread(descriptor, MAX_CREDENTIAL, 0), object_pairs_hook=unique)
    if not isinstance(value, dict) or set(value) != {
        "state",
        "capture_sha256",
        "rclone",
        "rclone_sha256",
        "key_generation",
        "escrow_drill_reference",
        "max_spool_bytes",
        "retention",
    }:
        raise BackupError("plan_shape")
    for name in (
        "state",
        "capture_sha256",
        "rclone",
        "rclone_sha256",
        "key_generation",
        "escrow_drill_reference",
    ):
        if not isinstance(value[name], str):
            raise BackupError("plan_shape")
    if (
        HASH.fullmatch(value["capture_sha256"]) is None
        or HASH.fullmatch(value["rclone_sha256"]) is None
        or REFERENCE.fullmatch(value["key_generation"]) is None
        or REFERENCE.fullmatch(value["escrow_drill_reference"]) is None
        or type(value["max_spool_bytes"]) is not int
        or value["max_spool_bytes"] < RUN_BUDGET
        or any(
            value[key].startswith(("REPLACE", "UNSET"))
            for key in ("key_generation", "escrow_drill_reference")
        )
    ):
        raise BackupError("owner_inputs_required")
    retention = value["retention"]
    if not isinstance(retention, dict) or set(retention) != {"daily", "weekly", "monthly"}:
        raise BackupError("retention_shape")
    if any(type(retention[key]) is not int for key in retention):
        raise BackupError("retention_shape")
    state, binary = Path(value["state"]), Path(value["rclone"])
    if not state.is_absolute() or not binary.is_absolute() or ".." in state.parts:
        raise BackupError("absolute_paths")
    return Plan(
        state,
        value["capture_sha256"],
        binary,
        value["rclone_sha256"],
        value["key_generation"],
        value["escrow_drill_reference"],
        value["max_spool_bytes"],
        Retention(retention["daily"], retention["weekly"], retention["monthly"]),
    )


def crypt_config(descriptor: int) -> None:
    config = configparser.ConfigParser(interpolation=None, strict=True)
    config.read_string(os.pread(descriptor, MAX_CREDENTIAL, 0).decode())
    if set(config.sections()) != {"media_s3", "source_media", "backup_s3", "backup_crypt"}:
        raise BackupError("rclone_sections")
    crypt = config["backup_crypt"]
    if (
        crypt.get("type") != "crypt"
        or crypt.get("filename_encryption") != "standard"
        or crypt.get("directory_name_encryption") != "true"
        or re.fullmatch(
            r"backup_s3:[A-Za-z0-9._-]+/business-backups/crypt-v[1-9][0-9]*",
            crypt.get("remote", ""),
        )
        is None
        or not all(crypt.get(key) for key in ("password", "password2"))
        or crypt.get("password") == crypt.get("password2")
    ):
        raise BackupError("crypt_required")
    source = config["source_media"]
    if source.get("type") != "alias" or not source.get("remote", "").startswith("media_s3:"):
        raise BackupError("scoped_source_alias")
    for name in ("media_s3", "backup_s3"):
        section = config[name]
        endpoint = urlsplit(section.get("endpoint", ""))
        if (
            section.get("type") != "s3"
            or section.get("env_auth") != "false"
            or not section.get("access_key_id")
            or not section.get("secret_access_key")
            or endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
            or section.get("no_check_certificate", "false") != "false"
            or section.get("no_head", "false") != "false"
        ):
            raise BackupError("explicit_https_s3_required")


def state_lock(plan: Plan) -> int:
    info = plan.state.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != PRIVATE_DIRECTORY_MODE
    ):
        raise BackupError("state_metadata")
    descriptor = os.open(plan.state / "run.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def local_capacity(plan: Plan) -> Path:
    spool = plan.state / "spool"
    spool.mkdir(mode=0o700, exist_ok=True)
    if spool.is_symlink():
        raise BackupError("spool_symlink")
    quarantined = []
    for entry in spool.iterdir():
        quarantined.append(entry)
        if len(quarantined) >= MAX_QUARANTINED_RUNS:
            raise BackupError("quarantine_full")
        if entry.is_symlink() or not entry.is_dir() or RUN_ID.fullmatch(entry.name) is None:
            raise BackupError("unknown_spool_entry")
    used = 0
    for index, file in enumerate(spool.rglob("*")):
        if index >= MAX_SPOOL_ENTRIES or file.is_symlink():
            raise BackupError("spool_entry_bound")
        if file.is_file():
            used += file.stat().st_size
    directory = plan.state / "catalog"
    if directory.is_symlink():
        raise BackupError("catalog_symlink")
    if directory.exists():
        for count, _file in enumerate(directory.glob("*.json"), start=1):
            if count >= MAX_CATALOG:
                raise BackupError("catalog_full")
    if used + RUN_BUDGET > plan.max_spool_bytes or shutil.disk_usage(spool).free < RUN_BUDGET:
        raise BackupError("spool_capacity")
    return spool


async def native(plan: Plan, descriptor: int, args: tuple[str, ...]) -> bytes:
    process = await asyncio.create_subprocess_exec(
        str(plan.rclone),
        "--config",
        f"/proc/self/fd/{descriptor}",
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=NATIVE_ENV,
        pass_fds=(descriptor,),
        start_new_session=True,
    )
    try:
        async with asyncio.timeout(PHASE_SECONDS):
            result = await capture.collect(process, MAX_CREDENTIAL)
    finally:
        await capture.stop(process)
    return result


def transfer_args(
    action: str, source: str, target: str, files: Path | None, maximum: int
) -> tuple[str, ...]:
    if action not in {"copy", "copyto"}:
        raise BackupError("transfer_action")
    args = (
        action,
        source,
        target,
        "--immutable",
        "--no-traverse",
        "--transfers=1",
        "--checkers=1",
        "--buffer-size=0",
        "--max-buffer-memory=32Mi",
        "--s3-chunk-size=5Mi",
        "--s3-upload-concurrency=1",
        "--contimeout=5s",
        "--timeout=15s",
        "--retries=1",
        "--low-level-retries=1",
        "--stats=0",
        "--log-level=ERROR",
        "--max-transfer=" + str(maximum),
        "--cutoff-mode=hard",
    )
    return args if files is None else (*args, "--files-from-raw", str(files))


def media_keys(baseline: Path, output: Path) -> None:
    objects = inventory(load(baseline))
    capture.save(output, ("\n".join(str(item["key"]) for item in objects) + "\n").encode())


def media_verify(baseline: Path, root: Path) -> None:
    for item in inventory(load(baseline)):
        key = item["key"]
        if not isinstance(key, str):
            raise BackupError("media_key")
        path = root
        for component in key.split("/"):
            path = path / component
            if path.is_symlink():
                raise BackupError("media_symlink")
        if path.stat().st_size != item["size"] or digest(path, MAX_OBJECT_BYTES) != item["sha256"]:
            raise BackupError("media_mismatch")


def manifest(payload: Path, run_id: str, output: Path) -> dict[str, object]:
    entries: list[dict[str, str | int]] = []
    for file in sorted(payload.rglob("*")):
        if file.is_symlink():
            raise BackupError("payload_symlink")
        if file.is_file():
            entries.append(
                {
                    "path": str(file.relative_to(payload)),
                    "size": file.stat().st_size,
                    "sha256": digest(file, MAX_DUMP_BYTES),
                }
            )
    if sum(int(item["size"]) for item in entries) > MAX_PAYLOAD:
        raise BackupError("payload_bound")
    value: dict[str, object] = {
        "format": 1,
        "run_id": run_id,
        "files": entries,
        "full_restore_proven": False,
    }
    capture.save(output, (json.dumps(value, sort_keys=True) + "\n").encode())
    return value


def catalog(plan: Plan, value: dict[str, object], run_id: str) -> None:
    directory = plan.state / "catalog"
    directory.mkdir(mode=0o700, exist_ok=True)
    capture.save(directory / (run_id + ".json"), (json.dumps(value) + "\n").encode())
    records = []
    for index, file in enumerate(directory.glob("*.json")):
        if index >= MAX_CATALOG or file.stat().st_size > MAX_CATALOG_RECORD:
            raise BackupError("catalog_bound")
        item = load(file)
        name, at = item.get("run_id"), item.get("verified_at")
        if (
            not isinstance(name, str)
            or RUN_ID.fullmatch(name) is None
            or not isinstance(at, str)
            or item.get("encrypted_remote_readback_verified") is not True
            or file.stem != name
        ):
            raise BackupError("catalog_shape")
        records.append(VerifiedRun(name, datetime.fromisoformat(at)))
    proposal = retention_plan(tuple(records), plan.retention)
    temporary = plan.state / (".retention-" + uuid4().hex)
    capture.save(temporary, (json.dumps(proposal) + "\n").encode())
    temporary.replace(plan.state / "retention-plan.json")


async def commit_verified(  # noqa: PLR0913 - fixed per-run commit evidence.
    plan: Plan,
    rclone_fd: int,
    payload: Path,
    run_id: str,
    run_path: Path,
    *,
    readback: dict[str, object],
) -> None:
    remote = "backup_crypt:runs/" + run_id
    committed: dict[str, object] = {
        "run_id": run_id,
        "verified_at": datetime.now(UTC).isoformat(),
        "key_generation": plan.key_generation,
        "escrow_drill_reference": plan.escrow_drill_reference,
        "manifest_sha256": digest(payload / "manifest.json", MAX_JSON),
        "encrypted_remote_readback_verified": True,
        "readback_mode": "native_sha256_download",
        "readback": readback,
        "plaintext_readback_tree_created": False,
        "full_restore_proven": False,
    }
    marker = run_path / "COMMITTED.json"
    capture.save(marker, (json.dumps(committed) + "\n").encode())
    await native(
        plan,
        rclone_fd,
        transfer_args("copyto", str(marker), remote + "/COMMITTED.json", None, MAX_JSON),
    )
    from deployment.backup.streaming import Expected, verify_remote

    await verify_remote(
        plan,
        rclone_fd,
        remote,
        {
            "COMMITTED.json": Expected(marker.stat().st_size, digest(marker, MAX_JSON)),
        },
        MAX_JSON,
        selected=("COMMITTED.json",),
    )
    await asyncio.to_thread(catalog, plan, committed, run_id)


def begin_run(plan: Plan) -> tuple[str, Path, Path]:
    spool = local_capacity(plan)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex
    directory = spool / run_id
    directory.mkdir(mode=0o700)
    payload = directory / "payload"
    payload.mkdir(mode=0o700)
    return run_id, directory, payload


async def run(
    plan: Plan,
    source_fd: int,
    password_fd: int,
    rclone_fd: int,
    ca_fd: int | None,
) -> None:
    lock = state_lock(plan)
    run_path: Path | None = None
    run_id: str | None = None
    verified = False
    try:
        if digest(Path(capture.__file__), MAX_JSON) != plan.capture_sha256:
            raise BackupError("capture_code_pin")
        if capture.binary_hash(plan.rclone) != plan.rclone_sha256:
            raise BackupError("rclone_code_pin")
        crypt_config(rclone_fd)
        if not (await native(plan, rclone_fd, ("version",))).startswith(b"rclone v1.76.0\n"):
            raise BackupError("rclone_version")
        run_id, run_path, payload = begin_run(plan)
        request = capture.read_request(source_fd)
        await capture.capture(
            replace(request, destination=payload / "database"), password_fd, ca_fd
        )
        receipt = load(payload / "database/complete.json")
        baseline = payload / "database/baseline.json"
        if (
            receipt.get("database_capture_complete") is not True
            or digest(payload / "database/source.dump", MAX_DUMP_BYTES)
            != receipt.get("source_dump_sha256")
            or digest(baseline, MAX_JSON) != receipt.get("baseline_sha256")
        ):
            raise BackupError("capture_receipt")
        keys = run_path / "media-keys.private"
        media_keys(baseline, keys)
        media = payload / "media"
        media.mkdir(mode=0o700)
        await native(
            plan,
            rclone_fd,
            transfer_args("copy", "source_media:", str(media), keys, MAX_MEDIA_BYTES),
        )
        await asyncio.to_thread(media_verify, baseline, media)
        await asyncio.to_thread(manifest, payload, run_id, payload / "manifest.json")
        paths = run_path / "payload-files.private"
        capture.save(
            paths,
            (
                "\n".join(
                    str(f.relative_to(payload)) for f in sorted(payload.rglob("*")) if f.is_file()
                )
                + "\n"
            ).encode(),
        )
        remote = "backup_crypt:runs/" + run_id
        await native(
            plan,
            rclone_fd,
            transfer_args("copy", str(payload), remote + "/payload", paths, MAX_PAYLOAD),
        )
        from deployment.backup.streaming import expected_payload, verify_remote

        expected = await asyncio.to_thread(expected_payload, payload)
        readback = await verify_remote(plan, rclone_fd, remote + "/payload", expected, MAX_PAYLOAD)
        await commit_verified(plan, rclone_fd, payload, run_id, run_path, readback=readback)
        # Only this newly owned successful run is removed; failure plaintext remains quarantined.
        await asyncio.to_thread(shutil.rmtree, run_path)
        run_path = None
        verified = True
    finally:
        if run_path is not None:
            with contextlib.suppress(OSError):
                capture.save(
                    run_path / "FAILED.json",
                    b'{"status":"failed","remote_commit_uncertain":true}\n',
                )
        try:
            await asyncio.to_thread(result_status, plan, verified, run_id)
        finally:
            os.close(lock)


def result_status(plan: Plan, verified: bool, run_id: str | None) -> None:
    latest = plan.state / "last-verified.json"
    if verified:
        item = {"verified_at": datetime.now(UTC).isoformat(), "run_id": run_id}
        temporary = plan.state / (".status-" + uuid4().hex)
        capture.save(temporary, (json.dumps(item) + "\n").encode())
        temporary.replace(latest)
    last_verified: object = load(latest).get("verified_at") if latest.exists() else None
    result = {
        "attempt_at": datetime.now(UTC).isoformat(),
        "success": verified,
        "last_verified_at": last_verified,
        "full_restore_proven": False,
    }
    temporary = plan.state / (".result-" + uuid4().hex)
    capture.save(temporary, (json.dumps(result) + "\n").encode())
    temporary.replace(plan.state / "last-result.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "source", "pgpass", "rclone"):
        parser.add_argument("--" + name + "-fd", type=int, required=True)
    parser.add_argument("--ca-fd", type=int)
    args = parser.parse_args()
    os.umask(0o077)
    opened: list[int] = []
    try:
        opened.extend(
            sealed_input(value)
            for value in (args.plan_fd, args.source_fd, args.pgpass_fd, args.rclone_fd)
        )
        ca = sealed_input(args.ca_fd) if args.ca_fd is not None else None
        if ca is not None:
            opened.append(ca)
        plan = read_plan(opened[0])

        async def execute() -> None:
            task = asyncio.current_task()
            if task is None:
                raise BackupError("task")
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
            await run(plan, opened[1], opened[2], opened[3], ca)

        asyncio.run(execute())
    except (
        OSError,
        ValueError,
        configparser.Error,
        TimeoutError,
        asyncio.CancelledError,
        KeyboardInterrupt,
    ):
        sys.stderr.write('{"event":"backup_failed","status":1}\n')
        return 1
    finally:
        for descriptor in opened:
            os.close(descriptor)
    sys.stdout.write('{"event":"backup_remote_readback_verified","full_restore_proven":false}\n')
    return 0


if __name__ == "__main__":
    sys.exit(main())
