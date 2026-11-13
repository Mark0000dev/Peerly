"""FD-only versioned-root rotation guard and native streamed escrow-canary readback."""

import argparse
import asyncio
import configparser
import hashlib
import json
import os
import re
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from deployment.backup.run_backup import (
    HASH,
    MAX_CREDENTIAL,
    REFERENCE,
    Plan,
    native,
    read_plan,
    sealed_input,
)
from deployment.backup.streaming import Expected, verify_remote
from deployment.restore import capture_backup as capture
from deployment.restore.accept_restore import unique

ROOT = re.compile(r"backup_s3:([A-Za-z0-9._-]+)/business-backups/crypt-v([1-9][0-9]{0,5})")
MAX_CANARY = 4096


class KeyRecoveryError(ValueError):
    """Closed key-operation failure, no secret/root/response contents attached."""


def profile(descriptor: int) -> configparser.ConfigParser:
    config = configparser.ConfigParser(interpolation=None, strict=True)
    raw = os.pread(descriptor, MAX_CREDENTIAL + 1, 0)
    if len(raw) > MAX_CREDENTIAL:
        raise KeyRecoveryError("escrow_profile_bound")
    config.read_string(raw.decode())
    if config.defaults() or set(config.sections()) != {"backup_s3", "backup_crypt"}:
        raise KeyRecoveryError("escrow_only_profile_required")
    transport, crypt = config["backup_s3"], config["backup_crypt"]
    if set(transport) - {
        "type",
        "provider",
        "env_auth",
        "endpoint",
        "region",
        "access_key_id",
        "secret_access_key",
        "force_path_style",
        "no_check_bucket",
        "no_head",
        "no_check_certificate",
    } or set(crypt) != {
        "type",
        "remote",
        "filename_encryption",
        "directory_name_encryption",
        "password",
        "password2",
    }:
        raise KeyRecoveryError("escrow_profile_options")
    endpoint = urlsplit(transport.get("endpoint", ""))
    if (
        transport.get("type") != "s3"
        or transport.get("env_auth") != "false"
        or endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username is not None
        or endpoint.path
        or endpoint.query
        or endpoint.fragment
        or transport.get("no_check_certificate", "false") != "false"
        or transport.get("no_head", "false") != "false"
        or not transport.get("access_key_id")
        or not transport.get("secret_access_key")
        or crypt.get("type") != "crypt"
        or crypt.get("filename_encryption") != "standard"
        or crypt.get("directory_name_encryption") != "true"
        or ROOT.fullmatch(crypt.get("remote", "")) is None
        or not crypt.get("password")
        or not crypt.get("password2")
        or crypt.get("password") == crypt.get("password2")
    ):
        raise KeyRecoveryError("escrow_profile_shape")
    return config


def rotation(old: Plan, new: Plan, old_fd: int, new_fd: int) -> dict[str, object]:
    before, after = profile(old_fd), profile(new_fd)
    old_crypt, new_crypt = before["backup_crypt"], after["backup_crypt"]
    old_root, new_root = (ROOT.fullmatch(c["remote"]) for c in (old_crypt, new_crypt))
    if old_root is None or new_root is None:
        raise KeyRecoveryError("crypt_root")
    if (
        old.state != new.state
        or old.max_spool_bytes != new.max_spool_bytes
        or old.rclone != new.rclone
        or old.rclone_sha256 != new.rclone_sha256
        or old.retention != new.retention
        or before["backup_s3"].get("endpoint") != after["backup_s3"].get("endpoint")
        or old_root[1] != new_root[1]
    ):
        raise KeyRecoveryError("rotation_scope_changed")
    same_material = all(old_crypt[k] == new_crypt[k] for k in ("password", "password2"))
    if old.key_generation == new.key_generation:
        if old_crypt["remote"] != new_crypt["remote"] or not same_material:
            raise KeyRecoveryError("unversioned_key_change")
    elif (
        int(new_root[2]) <= int(old_root[2])
        or any(old_crypt[k] == new_crypt[k] for k in ("password", "password2"))
        or old.escrow_drill_reference == new.escrow_drill_reference
    ):
        raise KeyRecoveryError("new_generation_root_and_drill_required")
    return {
        "status": "rotation_mapping_validated",
        "old_root_sha256": hashlib.sha256(old_crypt["remote"].encode()).hexdigest(),
        "new_root_sha256": hashlib.sha256(new_crypt["remote"].encode()).hexdigest(),
        "plaintext_key_distinctness_proven": False,
        "independent_custody_proven": False,
        "historical_roots_must_be_retained": True,
        "remote_deletion_enabled": False,
    }


def specification(
    descriptor: int, plan: Plan, config: configparser.ConfigParser
) -> dict[str, object]:
    raw = os.pread(descriptor, MAX_CREDENTIAL + 1, 0)
    if len(raw) > MAX_CREDENTIAL:
        raise KeyRecoveryError("canary_specification_bound")
    value: object = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict) or set(value) != {
        "key_generation",
        "canary_reference",
        "size",
        "sha256",
        "crypt_root_sha256",
        "endpoint_sha256",
    }:
        raise KeyRecoveryError("canary_specification")
    root_sha = hashlib.sha256(config["backup_crypt"]["remote"].encode()).hexdigest()
    if (
        value["key_generation"] != plan.key_generation
        or not isinstance(value["canary_reference"], str)
        or REFERENCE.fullmatch(value["canary_reference"]) is None
        or type(value["size"]) is not int
        or not 0 < value["size"] <= MAX_CANARY
        or not isinstance(value["sha256"], str)
        or HASH.fullmatch(value["sha256"]) is None
        or value["crypt_root_sha256"] != root_sha
        or value["endpoint_sha256"]
        != hashlib.sha256(config["backup_s3"]["endpoint"].encode()).hexdigest()
    ):
        raise KeyRecoveryError("canary_identity_or_bounds")
    return {key: item for key, item in value.items() if isinstance(key, str)}


async def verify(plan: Plan, config_fd: int, spec_fd: int) -> dict[str, object]:
    config = profile(config_fd)
    spec = specification(spec_fd, plan, config)
    if capture.binary_hash(plan.rclone) != plan.rclone_sha256:
        raise KeyRecoveryError("rclone_pin")
    if not (await native(plan, config_fd, ("version",))).startswith(b"rclone v1.76.0\n"):
        raise KeyRecoveryError("rclone_version")
    reference, size, hashed = spec["canary_reference"], spec["size"], spec["sha256"]
    if not isinstance(reference, str) or not isinstance(size, int) or not isinstance(hashed, str):
        raise KeyRecoveryError("canary_specification")
    readback = await verify_remote(
        plan,
        config_fd,
        "backup_crypt:key-recovery/" + reference,
        {"KEY-RECOVERY.json": Expected(size, hashed)},
        MAX_CANARY,
    )
    return {
        "event": "backup_key_canary_readback_verified",
        "verified_at": datetime.now(UTC).isoformat(),
        "key_generation": plan.key_generation,
        "escrow_drill_reference": plan.escrow_drill_reference,
        "crypt_root_sha256": spec["crypt_root_sha256"],
        "canary_sha256": hashed,
        "readback": readback,
        "native_key_readback_verified": True,
        "independent_custody_proven": False,
        "full_restore_proven": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    readback = sub.add_parser("verify")
    for name in ("plan", "escrow", "spec"):
        readback.add_argument("--" + name + "-fd", type=int, required=True)
    readback.add_argument("--receipt", type=Path, required=True)
    guarded = sub.add_parser("check-rotation")
    for name in ("old-plan", "new-plan", "old-escrow", "new-escrow"):
        guarded.add_argument("--" + name + "-fd", type=int, required=True)
    guarded.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    descriptors: list[int] = []
    try:
        if args.action == "verify":
            descriptors.extend(
                sealed_input(fd) for fd in (args.plan_fd, args.escrow_fd, args.spec_fd)
            )

            async def execute() -> dict[str, object]:
                task = asyncio.current_task()
                if task is None:
                    raise KeyRecoveryError("missing_task")
                asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
                return await verify(read_plan(descriptors[0]), descriptors[1], descriptors[2])

            result = asyncio.run(execute())
        else:
            descriptors.extend(
                sealed_input(fd)
                for fd in (
                    args.old_plan_fd,
                    args.new_plan_fd,
                    args.old_escrow_fd,
                    args.new_escrow_fd,
                )
            )
            result = rotation(
                read_plan(descriptors[0]), read_plan(descriptors[1]), descriptors[2], descriptors[3]
            )
        parent = args.receipt.parent.lstat()
        if (
            parent.st_uid != os.geteuid()
            or parent.st_mode & 0o077
            or args.receipt.parent.is_symlink()
        ):
            raise KeyRecoveryError("private_receipt_directory")
        capture.save(args.receipt, (json.dumps(result, sort_keys=True) + "\n").encode())
    except (
        OSError,
        ValueError,
        configparser.Error,
        TimeoutError,
        asyncio.CancelledError,
        KeyboardInterrupt,
    ):
        sys.stderr.write('{"event":"backup_key_operation_failed"}\n')
        return 1
    finally:
        for fd in descriptors:
            os.close(fd)
    sys.stdout.write('{"event":"backup_key_operation_recorded","full_restore_proven":false}\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
