"""Hold PID1 for explicit owner configuration, then exec the existing AI worker.

No application imports, credential reads, login, provider calls or readiness grants.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import stat
import sys
import threading
import time
from pathlib import Path

CONFIGURATION = Path("/var/lib/peerly-ai/acceptance/worker-env.json")
MAX_BYTES = 32768
MAX_VALUE = 8192
ALLOWED = frozenset(
    {
        "DATABASE_URL",
        *(
            f"MEDIA__{name}"
            for name in (
                "ENDPOINT_ORIGIN",
                "BUCKET",
                "REGION",
                "ACCESS_KEY_ID",
                "SECRET_ACCESS_KEY",
            )
        ),
        *(
            f"RUNTIME__{name}"
            for name in (
                "EXECUTABLE",
                "EXPECTED_VERSION",
                "EXPECTED_SHA256",
                "MODEL",
                "CREDENTIAL_DIRECTORY",
                "EXPECTED_ACCOUNT",
                "EXPECTED_LOGIN_OWNER",
                "EXPECTED_OAUTH_ISSUER",
                "EXPECTED_OAUTH_CLIENT_ID",
                "ACCEPTANCE_ARTIFACT",
                "WORKSPACES_ROOT",
                "BUBBLEWRAP",
                "PRLIMIT",
                "MAX_PROCESSES",
            )
        ),
        *(
            f"OBSERVABILITY__{name}"
            for name in (
                "COLLECTOR_ORIGIN",
                "ENVIRONMENT",
                "RELEASE",
                "TRACE_QUEUE_CAPACITY",
            )
        ),
    }
)
BASE_ENVIRONMENT = {
    "PATH": "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin",
    "PYTHONPATH": "/app/src",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUNBUFFERED": "1",
    "HOME": "/nonexistent",
    "TMPDIR": "/tmp",  # noqa: S108 - dedicated container bounded tmpfs, never a host directory.
}


class InvalidConfigurationError(ValueError):
    """Deliberately content-free error for private configuration failures."""


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidConfigurationError("duplicate configuration key")
        result[key] = value
    return result


def load_configuration(path: Path = CONFIGURATION) -> dict[str, str]:
    """Descriptor-relative nofollow traversal and bounded same-file read."""
    if not path.is_absolute() or ".." in path.parts:
        raise InvalidConfigurationError("invalid configuration location")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            next_directory = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=directory,
            )
            os.close(directory)
            directory = next_directory
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=directory,
        )
    finally:
        os.close(directory)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid not in {0, os.geteuid()}
            or before.st_mode & 0o022
            or before.st_size > MAX_BYTES
            or before.st_nlink != 1
        ):
            raise InvalidConfigurationError("unsafe configuration metadata")
        data = bytearray()
        while len(data) <= MAX_BYTES:
            chunk = os.read(descriptor, min(4096, MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(descriptor)
        if len(data) > MAX_BYTES or (
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise InvalidConfigurationError("configuration changed during read")
    finally:
        os.close(descriptor)
    try:
        parsed: object = json.loads(data, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidConfigurationError("invalid configuration JSON") from error
    if not isinstance(parsed, dict) or not parsed:
        raise InvalidConfigurationError("configuration must be a nonempty object")
    result: dict[str, str] = {}
    for key, value in parsed.items():
        if (
            not isinstance(key, str)
            or key not in ALLOWED
            or not isinstance(value, str)
            or not value
            or len(value) > MAX_VALUE
            or "\x00" in value
            or "\n" in value
            or "\r" in value
        ):
            raise InvalidConfigurationError("invalid configuration entry")
        result[key] = value
    return result


def activate(configuration: dict[str, str]) -> None:
    # Replace, never inherit ambient credentials, loader overrides or Codex config.
    os.execve(  # noqa: S606 - fixed interpreter/module; intentional same-PID replacement.
        sys.executable,
        (sys.executable, "-m", "studymate.ai_worker"),
        BASE_ENVIRONMENT | configuration,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=1800,
        choices=range(1, 3601),
        metavar="1..3600",
    )
    options = parser.parse_args()
    stopped = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda _number, _frame: stopped.set())
    deadline = time.monotonic() + options.wait_seconds
    sys.stdout.write("AI provisioning hold: awaiting owner configuration\n")
    sys.stdout.flush()
    while not stopped.is_set():
        if time.monotonic() >= deadline:
            sys.stderr.write("AI provisioning hold expired\n")
            return 1
        try:
            configuration = load_configuration()
        except FileNotFoundError:
            stopped.wait(min(1.0, max(0.0, deadline - time.monotonic())))
            continue
        except (OSError, ValueError):
            sys.stderr.write("AI provisioning configuration rejected\n")
            return 1
        if stopped.is_set():
            break
        activate(configuration)
        raise RuntimeError("execve unexpectedly returned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
