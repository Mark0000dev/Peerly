"""Offline evidence checking and a reviewable local disposable-PG restore command plan."""

import argparse
import hashlib
import json
import os
import re
import shlex
import stat
import sys
from pathlib import Path
from uuid import uuid4

MIN_PORT = 1024
MAX_PORT = 65535
DEFAULT_PG_PORT = 5432
MAX_TABLES = 256
MAX_ROWS = 10000
MAX_JSON = 8 * 1024 * 1024
MAX_OBJECTS = 20000
MAX_OBJECT_BYTES = 10000000
MAX_MEDIA_BYTES = 1024 * 1024 * 1024
MAX_DUMP_BYTES = 2 * 1024 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}")
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,62}")
KEY = re.compile(
    r"retained/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/"
    r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/(?:original|photo[.]jpg)"
)
REQUIRED = frozenset(
    {
        "accounts",
        "alembic_version",
        "photos",
        "photo_revisions",
        "photo_uploads",
        "photo_upload_revisions",
        "photo_processing_attempts",
        "messages",
        "conversations",
        "chat_image_preparations",
        "chat_image_revisions",
        "chat_image_attempts",
    }
)


class RejectedError(ValueError):
    """Closed failure; never print input, object keys, row data or native stderr."""


def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RejectedError("duplicate_json")
        result[key] = value
    return result


def load(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON:
        raise RejectedError("inventory_file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise RejectedError("inventory_file")
    value: object = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise RejectedError("inventory_shape")
    return {key: item for key, item in value.items() if isinstance(key, str)}


def digest(path: Path, limit: int) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise RejectedError("file_bounds")
        hashed = hashlib.sha256()
        total = 0
        while chunk := stream.read(min(65536, limit + 1 - total)):
            total += len(chunk)
            if total > limit:
                raise RejectedError("file_bounds")
            hashed.update(chunk)
        if total != info.st_size:
            raise RejectedError("file_changed")
        return hashed.hexdigest()


def inventory(data: dict[str, object]) -> list[dict[str, object]]:
    if (
        set(data)
        != {
            "format",
            "heads",
            "tables",
            "broken_relationships",
            "unvalidated_constraints",
            "disabled_triggers",
            "objects",
        }
        or type(data["format"]) is not int
        or data["format"] != 1
    ):
        raise RejectedError("inventory_shape")
    for name in ("broken_relationships", "unvalidated_constraints", "disabled_triggers"):
        if type(data[name]) is not int or data[name] != 0:
            raise RejectedError("relationships_or_constraints")
    heads = data["heads"]
    if not isinstance(heads, list) or len(heads) != 1 or not isinstance(heads[0], str):
        raise RejectedError("schema_head")
    validate_tables(data["tables"])
    return validate_objects(data["objects"])


def validate_tables(tables: object) -> None:
    if not isinstance(tables, dict) or not tables.keys() >= REQUIRED or len(tables) > MAX_TABLES:
        raise RejectedError("table_inventory")
    for name, value in tables.items():
        if not isinstance(name, str) or IDENTIFIER.fullmatch(name) is None:
            raise RejectedError("table_inventory")
        if not isinstance(value, dict) or set(value) != {"rows", "sha256"}:
            raise RejectedError("table_inventory")
        count: object = value["rows"]
        hashed: object = value["sha256"]
        if type(count) is not int or not 0 <= count <= MAX_ROWS:
            raise RejectedError("row_bound")
        if not isinstance(hashed, str) or HEX.fullmatch(hashed) is None:
            raise RejectedError("table_digest")


def validate_objects(objects: object) -> list[dict[str, object]]:
    if not isinstance(objects, list) or not 0 < len(objects) <= MAX_OBJECTS:
        raise RejectedError("empty_or_unbounded_media")
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    total = 0
    for item in objects:
        if not isinstance(item, dict) or set(item) != {"key", "size", "sha256"}:
            raise RejectedError("object_metadata")
        key: object = item["key"]
        size: object = item["size"]
        hashed = item["sha256"]
        if not isinstance(key, str) or KEY.fullmatch(key) is None or key in seen:
            raise RejectedError("object_key")
        if type(size) is not int or not 0 < size <= MAX_OBJECT_BYTES:
            raise RejectedError("object_size")
        if not isinstance(hashed, str) or HEX.fullmatch(hashed) is None:
            raise RejectedError("object_digest")
        total += size
        if total > MAX_MEDIA_BYTES:
            raise RejectedError("media_bound")
        seen.add(key)
        result.append({"key": key, "size": size, "sha256": hashed})
    # Every accepted ready attempt needs both immutable renditions.
    for key in seen:
        stem = key.rsplit("/", 1)[0]
        if {stem + "/original", stem + "/photo.jpg"} - seen:
            raise RejectedError("missing_rendition")
    return result


def verify(baseline: Path, restored: Path, media: Path) -> dict[str, object]:
    expected, actual = load(baseline), load(restored)
    inventory(expected)
    objects = inventory(actual)
    if expected != actual:
        raise RejectedError("snapshot_mismatch")
    root = media.resolve(strict=True)
    if media.is_symlink() or not root.is_dir():
        raise RejectedError("media_root")
    for item in objects:
        key, size, hashed = item["key"], item["size"], item["sha256"]
        if not isinstance(key, str):
            raise RejectedError("object_key")
        candidate = root
        for component in key.split("/"):
            candidate = candidate / component
            if candidate.is_symlink():
                raise RejectedError("object_symlink")
        if candidate.stat().st_size != size or digest(candidate, MAX_OBJECT_BYTES) != hashed:
            raise RejectedError("media_bytes_mismatch")
    return {
        "event": "restore_acceptance",
        "status": "bounded_pg_media_match",
        "verified_objects": len(objects),
        "inventory_sha256": digest(restored, MAX_JSON),
        "full_restore_proven": False,
    }


def target_name(source: str, token: str) -> str:
    name = "peerly_restore_" + token + "_test"
    if (
        IDENTIFIER.fullmatch(source) is None
        or re.fullmatch(r"[0-9a-f]{32}", token) is None
        or source == name
    ):
        raise RejectedError("database_identity")
    return name


def plan(  # noqa: PLR0913 - explicit bounded local inputs, no ambient credentials.
    directory: Path,
    *,
    source: str,
    port: int,
    role: str,
    dump: Path,
    expected_sha256: str,
    baseline: Path,
    media: Path,
) -> Path:
    if (
        not MIN_PORT <= port <= MAX_PORT
        or port == DEFAULT_PG_PORT
        or IDENTIFIER.fullmatch(role) is None
    ):
        raise RejectedError("isolated_endpoint")
    if HEX.fullmatch(expected_sha256) is None or digest(dump, MAX_DUMP_BYTES) != expected_sha256:
        raise RejectedError("dump_digest")
    inventory(load(baseline))
    target = target_name(source, uuid4().hex)
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    directory = directory.resolve()
    helper = Path(__file__).resolve()
    sql = helper.with_name("acceptance.sql")
    # No ambient libpq service, password file, home or options. Isolated trust-only PG required.
    env = [
        "/usr/bin/env",
        "-i",
        "PATH=/usr/bin:/bin",
        "PGHOST=127.0.0.1",
        "PGPORT=" + str(port),
        "PGUSER=" + role,
        "PGCONNECT_TIMEOUT=3",
    ]

    def native(binary: str, *args: str) -> str:
        return shlex.join(
            [
                *env,
                "/usr/bin/timeout",
                "--kill-after=5s",
                "180s",
                "/usr/bin/" + binary,
                "--no-password",
                *args,
            ]
        )

    def python(*args: str) -> str:
        return shlex.join([*env, sys.executable, "-B", str(helper), *args])

    output = directory / "restored.json"
    evidence = directory / "evidence.json"
    check = python("check-dump", str(dump.resolve()), expected_sha256)
    accept = python("verify", str(baseline.resolve()), str(output), str(media.resolve()))
    role_query = "SELECT rolcreatedb AND NOT rolsuper FROM pg_roles WHERE rolname=current_user"
    lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        "umask 077",
        "created=0",
        "cleanup() {",
        "  status=$?",
        "  trap - EXIT",
        '  if [ "$created" = 1 ]; then',
        "    " + native("dropdb", target) + " || status=1",
        "  fi",
        '  exit "$status"',
        "}",
        "trap cleanup EXIT",
        "exec 2>" + shlex.quote(str(directory / "native.stderr.private")),
        check,
        # Refuse superuser; database must be owned by the dedicated CREATEDB drill role.
        'test "$('
        + native(
            "psql",
            "--no-psqlrc",
            "-Atq",
            "--dbname=postgres",
            "-c",
            role_query,
        )
        + ')" = t',
        native("createdb", "--template=template0", "--owner=" + role, target),
        "created=1",
        native(
            "psql",
            "--no-psqlrc",
            "--set=ON_ERROR_STOP=1",
            "-q",
            "--dbname=" + target,
            "-c",
            'REVOKE CONNECT ON DATABASE "'
            + target
            + '" FROM PUBLIC; '
            + 'ALTER DATABASE "'
            + target
            + '" CONNECTION LIMIT 1',
        ),
        native(
            "pg_restore",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
            "--no-tablespaces",
            "--dbname=" + target,
            str(dump.resolve()),
        ),
        native(
            "psql",
            "--no-psqlrc",
            "--set=ON_ERROR_STOP=1",
            "-Atq",
            "--dbname=" + target,
            "--file=" + str(sql),
        )
        + " >"
        + shlex.quote(str(output)),
        "/usr/bin/timeout --kill-after=5s 600s " + accept + " >" + shlex.quote(str(evidence)),
    ]
    script = directory / "restore.sh"
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o700)
    return script


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check-dump")
    check.add_argument("dump", type=Path)
    check.add_argument("sha256")
    accept = sub.add_parser("verify")
    for name in ("baseline", "restored", "media"):
        accept.add_argument(name, type=Path)
    generate = sub.add_parser("plan")
    for name in ("directory", "dump", "baseline", "media"):
        generate.add_argument("--" + name, required=True, type=Path)
    for name in ("source", "role", "sha256"):
        generate.add_argument("--" + name, required=True)
    generate.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    try:
        if args.command == "check-dump":
            if digest(args.dump, MAX_DUMP_BYTES) != args.sha256:
                raise RejectedError("dump_digest")
        elif args.command == "verify":
            sys.stdout.write(json.dumps(verify(args.baseline, args.restored, args.media)) + "\n")
        else:
            plan(
                args.directory,
                source=args.source,
                port=args.port,
                role=args.role,
                dump=args.dump,
                expected_sha256=args.sha256,
                baseline=args.baseline,
                media=args.media,
            )
    except (OSError, ValueError):
        sys.stderr.write("restore_acceptance_rejected\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
