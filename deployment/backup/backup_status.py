"""Bounded metadata-only backup status for the existing protected metrics gateway."""

import argparse
import json
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from deployment.backup.run_backup import RUN_ID
from deployment.restore.accept_restore import unique

MAX_STATUS = 16384
MAX_CLOCK_SKEW = 300
MAX_TIME_TEXT = 64
MAX_RUN_SECONDS = 35 * 60
UNIT_RESULTS = frozenset(
    {
        "success",
        "resources",
        "timeout",
        "exit-code",
        "signal",
        "core-dump",
        "watchdog",
        "start-limit-hit",
        "oom-kill",
        "protocol",
        "exec-condition",
        "unknown",
    }
)
METRICS = (
    "status_valid",
    "last_verified_timestamp_seconds",
    "last_attempt_timestamp_seconds",
    "last_attempt_success",
    "unit_result_known",
    "unit_success",
)


class StatusError(ValueError):
    """No private input or filename is attached to a status failure."""


def metadata(directory: int, name: str) -> dict[str, object]:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
            or not 0 < info.st_size <= MAX_STATUS
        ):
            raise StatusError("metadata_file")
        raw = stream.read(MAX_STATUS + 1)
    if len(raw) > MAX_STATUS:
        raise StatusError("metadata_bound")
    value: object = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise StatusError("metadata_shape")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def epoch(value: object, now: datetime) -> float:
    if not isinstance(value, str) or len(value) > MAX_TIME_TEXT:
        raise StatusError("metadata_time")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None or not 0 < parsed.timestamp() <= now.timestamp() + MAX_CLOCK_SKEW:
        raise StatusError("metadata_time")
    return parsed.timestamp()


def verified_epoch(directory: int, result: dict[str, object], now: datetime) -> float:
    if result["last_verified_at"] is None:
        if result["success"]:
            raise StatusError("success_without_verified_generation")
        return 0.0
    latest = metadata(directory, "last-verified.json")
    if (
        set(latest) != {"verified_at", "run_id"}
        or latest["verified_at"] != result["last_verified_at"]
    ):
        raise StatusError("verified_shape")
    run = latest["run_id"]
    if not isinstance(run, str) or RUN_ID.fullmatch(run) is None:
        raise StatusError("verified_identity")
    catalog = os.open("catalog", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
    try:
        info = os.fstat(catalog)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise StatusError("catalog_directory")
        committed = metadata(catalog, run + ".json")
    finally:
        os.close(catalog)
    if (
        committed.get("run_id") != run
        or committed.get("full_restore_proven") is not False
        or committed.get("encrypted_remote_readback_verified") is not True
        or committed.get("plaintext_readback_tree_created") is not False
        or committed.get("readback_mode") != "native_sha256_download"
    ):
        raise StatusError("verified_catalog")
    verified = epoch(latest["verified_at"], now)
    if (
        not -MAX_CLOCK_SKEW
        <= verified - epoch(committed.get("verified_at"), now)
        <= (MAX_RUN_SECONDS + MAX_CLOCK_SKEW)
    ):
        raise StatusError("catalog_status_time")
    return verified


def snapshot(state: Path, unit_result: str, now: datetime) -> dict[str, float]:
    if unit_result not in UNIT_RESULTS or now.utcoffset() is None:
        raise StatusError("unit_result")
    values = dict.fromkeys(METRICS, 0.0)
    values["unit_result_known"] = float(unit_result != "unknown")
    values["unit_success"] = float(unit_result == "success")
    directory = None
    try:
        directory = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(directory)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise StatusError("state_directory")
        result = metadata(directory, "last-result.json")
        if set(result) != {"attempt_at", "success", "last_verified_at", "full_restore_proven"}:
            raise StatusError("result_shape")
        if type(result["success"]) is not bool or result["full_restore_proven"] is not False:
            raise StatusError("result_shape")
        values["last_attempt_timestamp_seconds"] = epoch(result["attempt_at"], now)
        values["last_attempt_success"] = float(result["success"] is True)
        values["last_verified_timestamp_seconds"] = verified_epoch(directory, result, now)
        if (
            values["last_verified_timestamp_seconds"]
            > values["last_attempt_timestamp_seconds"] + MAX_CLOCK_SKEW
        ):
            raise StatusError("inconsistent_status_time")
        if (
            result["success"] is True
            and abs(
                values["last_verified_timestamp_seconds"] - values["last_attempt_timestamp_seconds"]
            )
            > MAX_CLOCK_SKEW
        ):
            raise StatusError("inconsistent_success_time")
        values["status_valid"] = 1.0
    except (OSError, ValueError):
        # Explicit invalid state, never fabricate a successful absent sample.
        for name in METRICS[:4]:
            values[name] = 0.0
    finally:
        if directory is not None:
            os.close(directory)
    return values


def render(values: dict[str, float]) -> bytes:
    return (
        "\n".join(
            "# TYPE peerly_backup_"
            + name
            + " gauge\npeerly_backup_"
            + name
            + " "
            + str(values[name])
            for name in METRICS
        )
        + "\n"
    ).encode()


def publish(output: Path, data: bytes) -> None:
    directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".backup-" + uuid4().hex
    try:
        parent = os.fstat(directory)
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o022 or len(data) > MAX_STATUS:
            raise StatusError("metrics_directory")
        try:
            old = os.stat(output.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            old = None
        if old is not None and (not stat.S_ISREG(old.st_mode) or old.st_uid != os.geteuid()):
            raise StatusError("metrics_destination")
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)  # Fixed numeric metadata only, no secret fields.
            os.fsync(stream.fileno())
        os.replace(temporary, output.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        finally:
            os.close(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--unit-result",
        choices=sorted(UNIT_RESULTS),
        default=os.environ.get("SERVICE_RESULT", "unknown"),
    )
    args = parser.parse_args()
    try:
        publish(args.output, render(snapshot(args.state, args.unit_result, datetime.now(UTC))))
    except (OSError, ValueError):
        sys.stderr.write('{"event":"backup_status_publish_failed"}\n')
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
