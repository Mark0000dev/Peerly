"""Fixed Peerly backup closure installation; never starts/enables a timer or reads secrets."""

import argparse
import ast
import fcntl
import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
import sys
from pathlib import Path

MAX_FILE = 1024 * 1024
MAX_MANIFEST = 16384
MAX_CREDENTIAL = 65536
ROOT_UID = 0
BASE = Path("/usr/local/lib/peerly-backup")
STATE = Path("/var/lib/peerly-backup")
METRICS = Path("/var/lib/peerly-backup-metrics")
CONFIG = Path("/etc/peerly-backup")
UNITS = Path("/etc/systemd/system")
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C", "PYTHONDONTWRITEBYTECODE": "1"}
RUNTIME = (
    "deployment/backup/run_backup.py",
    "deployment/backup/streaming.py",
    "deployment/backup/retention.py",
    "deployment/backup/backup_status.py",
    "deployment/backup/key_recovery.py",
    "deployment/backup/run-installed-backup.sh",
    "deployment/restore/accept_restore.py",
    "deployment/restore/capture_backup.py",
    "deployment/restore/acceptance.sql",
    "deployment/restore/recovery_catalog.sql",
    "deployment/restore/recovery_checks.py",
    "deployment/restore/recovery_and.py",
)
TEMPLATES = {
    "peerly-backup.service": "deployment/backup/peerly-backup.service.template",
    "peerly-backup-failed.service": "deployment/backup/peerly-backup-failed.service.template",
    "peerly-backup.timer": "deployment/backup/peerly-backup.timer.example",
}
FILES = frozenset((*RUNTIME, *TEMPLATES.values()))
SAFE_PYTHON = re.compile(r"/[A-Za-z0-9_./-]+")


class InstallError(ValueError):
    """Closed installation errors, never credential contents/native stderr."""


def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InstallError("manifest_duplicate")
        result[key] = value
    return result


def read_file(root: Path, relative: str, limit: int = MAX_FILE) -> bytes:
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = relative.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise InstallError("source_path")
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(file, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                raise InstallError("source_file")
            value = stream.read(limit + 1)
        if len(value) > limit:
            raise InstallError("source_bound")
        return value
    finally:
        os.close(descriptor)


def save(path: Path, data: bytes, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())


def validate_sql_pins(contents: dict[str, bytes]) -> None:
    module = ast.parse(contents["deployment/restore/capture_backup.py"])
    values: dict[str, str] = {}
    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = node.value.value
    for label, filename in (
        ("SQL_SHA256", "acceptance.sql"),
        ("CATALOG_SQL_SHA256", "recovery_catalog.sql"),
    ):
        if (
            values.get(label)
            != hashlib.sha256(contents["deployment/restore/" + filename]).hexdigest()
        ):
            raise InstallError("matched_capture_sql_pins_required")


def prepare(source: Path, output: Path) -> str:
    contents = {name: read_file(source, name) for name in sorted(FILES)}
    for name, data in contents.items():
        if name.endswith(".py"):
            compile(data, name, "exec")
    validate_sql_pins(contents)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, data in contents.items():
        target = output / name
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        save(target, data, 0o755 if name.endswith(".sh") else 0o644)
    manifest = (
        json.dumps(
            {
                "format": 1,
                "files": {
                    name: hashlib.sha256(data).hexdigest() for name, data in contents.items()
                },
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()
    save(output / "manifest.json", manifest)
    return hashlib.sha256(manifest).hexdigest()


def closure(bundle: Path, expected_sha256: str) -> dict[str, bytes]:
    raw = read_file(bundle, "manifest.json", MAX_MANIFEST)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise InstallError("manifest_pin")
    value: object = json.loads(raw, object_pairs_hook=unique)
    if (
        not isinstance(value, dict)
        or set(value) != {"format", "files"}
        or type(value["format"]) is not int
        or value["format"] != 1
    ):
        raise InstallError("manifest_shape")
    entries = value["files"]
    if not isinstance(entries, dict) or set(entries) != FILES:
        raise InstallError("fixed_source_closure")
    contents = {}
    for name in sorted(FILES):
        data = read_file(bundle, name)
        if hashlib.sha256(data).hexdigest() != entries[name]:
            raise InstallError("source_pin")
        contents[name] = data
    validate_sql_pins(contents)
    return contents


def render_units(
    contents: dict[str, bytes], release: Path, python: Path, with_ca: bool
) -> dict[str, bytes]:
    if (
        SAFE_PYTHON.fullmatch(str(python)) is None
        or ".." in python.parts
        or re.fullmatch(r"/usr/local/lib/peerly-backup/releases/[0-9a-f]{64}", str(release)) is None
    ):
        raise InstallError("installed_executable_path")
    result = {}
    for name, relative in TEMPLATES.items():
        text = (
            contents[relative]
            .decode()
            .replace("@@BACKUP_RELEASE@@", str(release))
            .replace("@@BACKUP_PYTHON@@", str(python))
        )
        ca = (
            "LoadCredential=pg-ca:/etc/peerly-backup/pg-ca.pem"
            if with_ca
            else "# No pg-ca credential: preserve explicit source-request SSL policy."
        )
        text = text.replace("@@BACKUP_OPTIONAL_CA@@", ca)
        if "@@" in text:
            raise InstallError("unit_placeholder")
        result[name] = text.encode()
    return result


def root_directory(path: Path) -> None:
    if not path.exists():
        path.mkdir(mode=0o755)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != ROOT_UID or info.st_mode & 0o022:
        raise InstallError("root_directory")


def trusted_path(path: Path, *, directory: bool) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise InstallError("root_path")
    current = Path("/")
    for part in path.parts[1:]:
        current /= part
        info = current.lstat()
        required_directory = current != path or directory
        if (
            info.st_uid != ROOT_UID
            or info.st_mode & 0o022
            or (required_directory and not stat.S_ISDIR(info.st_mode))
            or (not required_directory and not stat.S_ISREG(info.st_mode))
        ):
            raise InstallError("root_path")


def command(args: tuple[str, ...]) -> bytes:
    process = subprocess.run(  # noqa: S603 - fixed local tool argv/root-verified runtime, no shell or credentials.
        args,
        env=ENV,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )
    if process.returncode != 0 or len(process.stdout) > MAX_MANIFEST:
        raise InstallError("local_validation")
    return process.stdout


def credential_metadata(with_ca: bool) -> None:
    # Metadata only: never open the staged credential contents.
    trusted_path(CONFIG, directory=True)
    for name in (
        "plan.json",
        "source-request.json",
        "pgpass",
        "rclone.conf",
        *(("pg-ca.pem",) if with_ca else ()),
    ):
        info = (CONFIG / name).lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != ROOT_UID
            or info.st_mode & 0o077
            or not 0 < info.st_size <= MAX_CREDENTIAL
        ):
            raise InstallError("credential_metadata")


def install(
    bundle: Path, expected_sha256: str, python: Path, *, with_ca: bool
) -> dict[str, object]:
    if os.geteuid() != ROOT_UID:
        raise InstallError("root_install_required")
    contents = closure(bundle, expected_sha256)
    account = pwd.getpwnam("peerly-backup")
    if account.pw_uid == ROOT_UID:
        raise InstallError("dedicated_account_required")
    executable = python.resolve(strict=True)
    trusted_path(executable, directory=False)
    command(
        (
            str(executable),
            "-I",
            "-B",
            "-c",
            (
                "import sys,os,fcntl; assert sys.version_info >= (3,11); "
                "assert hasattr(os,'memfd_create'); assert hasattr(fcntl,'F_ADD_SEALS')"
            ),
        )
    )
    for name in ("peerly-backup.service", "peerly-backup.timer", "peerly-backup-failed.service"):
        if (UNITS / name).exists() or (UNITS / name).is_symlink():
            raise InstallError("existing_units_require_manual_reconciliation")
    credential_metadata(with_ca)
    trusted_path(BASE.parent, directory=True)
    trusted_path(UNITS, directory=True)
    root_directory(BASE.parent)
    root_directory(BASE)
    root_directory(BASE / "releases")
    lock = os.open(BASE / ".install.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = BASE / "releases" / expected_sha256
        release.mkdir(mode=0o755, exist_ok=False)
        for name in RUNTIME:
            target = release / name
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            save(target, contents[name], 0o755 if name.endswith(".sh") else 0o644)
        unit_files = render_units(contents, release, executable, with_ca)
        staged = release / "units"
        staged.mkdir(mode=0o755)
        for name, data in unit_files.items():
            save(staged / name, data)
        command(
            (
                str(executable),
                "-I",
                "-B",
                "-c",
                "import sys; sys.path.insert(0,"
                + repr(str(release))
                + "); from deployment.backup import run_backup,backup_status,key_recovery",
            )
        )
        command(
            ("/usr/bin/systemd-analyze", "verify", *(str(staged / name) for name in unit_files))
        )
        for path, mode in ((STATE, 0o700), (METRICS, 0o755)):
            if not path.exists():
                path.mkdir(mode=mode)
                os.chown(path, account.pw_uid, account.pw_gid)
            info = path.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != account.pw_uid
                or stat.S_IMODE(info.st_mode) != mode
            ):
                raise InstallError("owned_state_directory")
        for name, data in unit_files.items():
            save(UNITS / name, data)
        receipt: dict[str, object] = {
            "status": "installed_inactive",
            "source_manifest_sha256": expected_sha256,
            "release": str(release),
            "unit_names": sorted(unit_files),
            "capture_sha256": hashlib.sha256(
                contents["deployment/restore/capture_backup.py"]
            ).hexdigest(),
            "catalog_sql_sha256": hashlib.sha256(
                contents["deployment/restore/recovery_catalog.sql"]
            ).hexdigest(),
            "daemon_reload_required": True,
            "activation_performed": False,
            "credential_contents_read": False,
            "provider_contacted": False,
            "full_restore_proven": False,
        }
        save(release / "install-receipt.json", (json.dumps(receipt) + "\n").encode(), 0o600)
        return receipt
    finally:
        os.close(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="action", required=True)
    prepared = modes.add_parser("prepare")
    prepared.add_argument("--source", type=Path, required=True)
    prepared.add_argument("--output", type=Path, required=True)
    applied = modes.add_parser("install")
    applied.add_argument("--bundle", type=Path, required=True)
    applied.add_argument("--manifest-sha256", required=True)
    applied.add_argument("--python", type=Path, default=Path("/usr/bin/python3"))
    applied.add_argument("--with-ca", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            result: dict[str, object] = {
                "source_manifest_sha256": prepare(args.source, args.output),
                "activation_performed": False,
            }
        else:
            result = install(args.bundle, args.manifest_sha256, args.python, with_ca=args.with_ca)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        sys.stderr.write('{"event":"backup_install_failed"}\n')
        return 1
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
