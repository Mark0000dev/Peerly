"""Bounded native decrypted SHA256 readback; no raw decrypted output file/tree."""

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from deployment.restore import capture_backup as capture
from deployment.restore.accept_restore import MAX_DUMP_BYTES, MAX_JSON, digest, load, unique

if TYPE_CHECKING:
    from deployment.backup.run_backup import Plan

MAX_FILES = 20016
MAX_LISTING_BYTES = 16 * 1024 * 1024
MAX_HASH_LINE = 512
SECONDS = 600
HASH_LINE = re.compile(rb"([0-9a-f]{64})  ([A-Za-z0-9_./-]+)\n")
HASH_VALUE = re.compile(r"[0-9a-f]{64}")
ENVIRONMENT = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C",
    "LC_ALL": "C",
    "AWS_EC2_METADATA_DISABLED": "true",
    "GOMEMLIMIT": "160MiB",
}


class ReadbackError(ValueError):
    """Closed rejection: never include native stderr, names or raw file bytes."""


@dataclass(frozen=True, slots=True)
class Expected:
    size: int
    sha256: str


def safe_name(name: str) -> bool:
    return (
        bool(name)
        and len(name) <= MAX_HASH_LINE - 68
        and re.fullmatch(r"[A-Za-z0-9_./-]+", name) is not None
        and not name.startswith("/")
        and str(PurePosixPath(name)) == name
        and all(part not in {".", ".."} for part in name.split("/"))
    )


def expected_payload(payload: Path) -> dict[str, Expected]:
    value = load(payload / "manifest.json")
    entries = value.get("files")
    if not isinstance(entries, list) or not 0 < len(entries) < MAX_FILES:
        raise ReadbackError("expected_manifest")
    result: dict[str, Expected] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}:
            raise ReadbackError("expected_manifest")
        name, size, hashed = entry["path"], entry["size"], entry["sha256"]
        if (
            not isinstance(name, str)
            or not safe_name(name)
            or name in result
            or name == "manifest.json"
            or type(size) is not int
            or not 0 <= size <= MAX_DUMP_BYTES
            or not isinstance(hashed, str)
            or HASH_VALUE.fullmatch(hashed) is None
        ):
            raise ReadbackError("expected_manifest")
        result[name] = Expected(size, hashed)
    file = payload / "manifest.json"
    result["manifest.json"] = Expected(file.stat().st_size, digest(file, MAX_JSON))
    return result


def listing(raw: bytes, expected: dict[str, Expected]) -> int:
    if len(raw) > MAX_LISTING_BYTES:
        raise ReadbackError("listing_bound")
    values: object = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(values, list) or len(values) > MAX_FILES:
        raise ReadbackError("listing_shape")
    seen: set[str] = set()
    unknown = 0
    for value in values:
        if not isinstance(value, dict):
            raise ReadbackError("listing_shape")
        name, size, directory = value.get("Path"), value.get("Size"), value.get("IsDir")
        if (
            not isinstance(name, str)
            or not safe_name(name)
            or name not in expected
            or name in seen
            or type(size) is not int
            or directory is not False
        ):
            raise ReadbackError("listing_file_set")
        if size == -1:
            unknown += 1
        elif size != expected[name].size:
            raise ReadbackError("listing_size")
        seen.add(name)
    if seen != expected.keys():
        raise ReadbackError("listing_missing")
    return unknown


class Hashes:
    def __init__(self, expected: dict[str, Expected]) -> None:
        if not 0 < len(expected) <= MAX_FILES:
            raise ReadbackError("expected_count")
        self.expected = expected
        self.seen: set[str] = set()

    def line(self, raw: bytes) -> None:
        if len(raw) > MAX_HASH_LINE:
            raise ReadbackError("hash_line_bound")
        matched = HASH_LINE.fullmatch(raw)
        if matched is None:
            raise ReadbackError("hash_line_format")
        name = matched[2].decode("ascii")
        if not safe_name(name) or name not in self.expected or name in self.seen:
            raise ReadbackError("hash_file_set")
        if matched[1].decode("ascii") != self.expected[name].sha256:
            raise ReadbackError("hash_mismatch")
        self.seen.add(name)

    def finish(self, returncode: int) -> None:
        if returncode != 0:
            raise ReadbackError("hash_command_failed")
        if self.seen != self.expected.keys():
            raise ReadbackError("hash_missing")


def command(action: str, remote: str, maximum: int, selected: tuple[str, ...]) -> tuple[str, ...]:
    if action not in {"lsjson", "hashsum"}:
        raise ReadbackError("readback_action")
    args: tuple[str, ...] = (
        ("hashsum", "SHA256", remote, "--download")
        if action == "hashsum"
        else ("lsjson", remote, "--recursive", "--files-only", "--no-modtime", "--no-mimetype")
    )
    args += (
        "--checkers=1",
        "--transfers=1",
        "--buffer-size=0",
        "--max-buffer-memory=32Mi",
        "--contimeout=5s",
        "--timeout=15s",
        "--retries=1",
        "--low-level-retries=1",
        "--stats=0",
        "--log-level=ERROR",
        "--max-transfer=" + str(maximum),
        "--cutoff-mode=hard",
    )
    # Payload verifies the whole unique prefix. Only the root commit marker is separately selected.
    if selected:
        if selected != ("COMMITTED.json",):
            raise ReadbackError("readback_selection")
        args += ("--include=/COMMITTED.json",)
    return args


async def start(plan: "Plan", descriptor: int, args: tuple[str, ...]) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        str(plan.rclone),
        "--config",
        f"/proc/self/fd/{descriptor}",
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=ENVIRONMENT,
        pass_fds=(descriptor,),
        start_new_session=True,
        limit=MAX_HASH_LINE + 1,
    )


async def remote_listing(plan: "Plan", descriptor: int, args: tuple[str, ...]) -> bytes:
    process = await start(plan, descriptor, args)
    try:
        async with asyncio.timeout(SECONDS):
            return await capture.collect(process, MAX_LISTING_BYTES)
    finally:
        await capture.stop(process)


async def remote_hashes(
    plan: "Plan",
    descriptor: int,
    args: tuple[str, ...],
    expected: dict[str, Expected],
) -> None:
    process = await start(plan, descriptor, args)
    state = Hashes(expected)
    try:
        async with asyncio.timeout(SECONDS):
            if process.stdout is None:
                raise ReadbackError("hash_pipe")
            while True:
                try:
                    line = await process.stdout.readline()
                except ValueError:
                    raise ReadbackError("hash_line_bound") from None
                if not line:
                    break
                state.line(line)
            state.finish(await process.wait())
    finally:
        await capture.stop(process)


async def verify_remote(  # noqa: PLR0913 - fixed native readback inputs, no generic job API.
    plan: "Plan",
    descriptor: int,
    remote: str,
    expected: dict[str, Expected],
    maximum: int,
    *,
    selected: tuple[str, ...] = (),
) -> dict[str, object]:
    if sum(item.size for item in expected.values()) > maximum:
        raise ReadbackError("expected_bytes_bound")
    index_args = command("lsjson", remote, maximum, selected)
    before = listing(await remote_listing(plan, descriptor, index_args), expected)
    await remote_hashes(plan, descriptor, command("hashsum", remote, maximum, selected), expected)
    after = listing(await remote_listing(plan, descriptor, index_args), expected)
    return {
        "mode": "native_sha256_download",
        "verified_files": len(expected),
        "expected_bytes": sum(item.size for item in expected.values()),
        "unknown_size_files_before": before,
        "unknown_size_files_after": after,
        "plaintext_readback_tree_created": False,
    }
