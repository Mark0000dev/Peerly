"""Parent-installed host relay: one pinned container, sanitized metadata, native syslog.

No application imports, credentials/config reads, daemon discovery, Docker exec or
container mutation. TCP logger exit0 is not proof of Collector/Loki persistence.
"""

import argparse
import hashlib
import json
import math
import os
import queue
import re
import selectors
import signal
import stat
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Never

if TYPE_CHECKING:
    from collections.abc import Container

DOCKER = Path("/usr/bin/docker")
LOGGER = Path("/usr/bin/logger")
SOCKET = Path("/var/run/docker.sock")
STATE = Path("/var/lib/peerly-ai-log-relay")
CONFIG = STATE / "docker-config"
PRIVATE_MODE = 0o700
MAX_LINE = 16384
MAX_MESSAGE = 8192
MAX_BINARY = 128 * 1024 * 1024
QUEUE_SIZE = 64
CHUNK = 4096
SEND_SECONDS = 2
SELECT_SECONDS = 0.2
HEX_ID = re.compile(r"[0-9a-f]{64}")
RELEASE = re.compile(r"[0-9a-f]{40}")
TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.+-]{8,40}")
DOCKER_TIME = re.compile(rb"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]{8,30}Z ")
FILE = re.compile(
    r"([A-Za-z0-9_][A-Za-z0-9_.-]{0,123}[.]py|<(stdin|string|unknown)>|"
    r"<frozen [A-Za-z0-9_.]{1,96}>)"
)
FUNCTION = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]{0,127}|<(module|lambda|genexpr|listcomp|dictcomp|setcomp)>)"
)
ERROR_TYPE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
SQLSTATE = re.compile(r"[0-9A-Z]{5}")
MAX_STACK = 20
MAX_LOCATION = 2147483647
LEVELS = {
    "DEBUG": "debug",
    "INFO": "info",
    "WARNING": "warning",
    "ERROR": "err",
    "CRITICAL": "crit",
}
EVENTS = frozenset(
    {
        "worker_step",
        "worker_stopped",
        "worker_storage_unavailable",
        "runtime_error",
        "runtime_log",
        "ai_runtime_failure",
    }
)
PHASES = frozenset({"receipt_recheck", "heartbeat", "revoke", "physical_cleanup", "retire"})
CODES = frozenset(
    {
        "storage_unavailable",
        "ownership_lost",
        "receipt_rejected",
        "physical_stop_uncertain",
        "credential_uncertain",
        "cancelled",
        "unexpected",
    }
)
OUTCOMES = frozenset(
    {
        "idle",
        "changed",
        "delivered",
        "ready",
        "busy",
        "rejected",
        "expired",
        "cleaned",
        "retry",
        "failed",
        "skipped",
        "stale",
        "cancelled",
        "storage_unavailable",
        "unexpected_error",
    }
)
ENVIRONMENT = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "DOCKER_CONFIG": str(CONFIG),
}


class RejectedError(ValueError):
    """Content-free closed input rejection."""


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RejectedError("duplicate_key")
        result[key] = value
    return result


def reject_constant(_value: str) -> Never:
    raise RejectedError("nonfinite_json")


def member(value: object, allowed: "Container[str]") -> str:
    if not isinstance(value, str) or value not in allowed:
        raise RejectedError("invalid_metadata")
    return value


def matches(value: object, pattern: re.Pattern[str]) -> str | None:
    return value if isinstance(value, str) and pattern.fullmatch(value) is not None else None


def stack_metadata(value: object) -> list[dict[str, str | int]]:
    if not isinstance(value, list) or len(value) > MAX_STACK:
        return []
    frames: list[dict[str, str | int]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        filename = matches(item.get("file"), FILE)
        function = matches(item.get("function"), FUNCTION)
        line: object = item.get("line")
        if (
            filename is not None
            and function is not None
            and type(line) is int
            and 1 <= line <= MAX_LOCATION
        ):
            frames.append({"file": filename, "function": function, "line": line})
    return frames


def error_metadata(data: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, pattern in (("error_type", ERROR_TYPE), ("database_error_code", SQLSTATE)):
        value = matches(data.get(key), pattern)
        if value is not None:
            result[key] = value
    stack = stack_metadata(data.get("stack"))
    if stack:
        result["stack"] = stack
    return result


@dataclass(frozen=True, slots=True)
class Message:
    encoded: bytes
    priority: str


def sanitize(line: bytes) -> Message | None:
    """Reconstruct only known source metadata, never forward original log content."""
    if len(line) > MAX_LINE:
        return None
    prefix = DOCKER_TIME.match(line)
    if prefix is None:
        return None
    try:
        parsed: object = json.loads(
            line[prefix.end() :], object_pairs_hook=unique_object, parse_constant=reject_constant
        )
        if not isinstance(parsed, dict):
            return None
        data: dict[str, object] = {
            key: value for key, value in parsed.items() if isinstance(key, str)
        }
        event = member(data.get("event"), EVENTS)
        level = member(data.get("level"), LEVELS)
        release = matches(data.get("service_release"), RELEASE)
        when = matches(data.get("time"), TIME)
        if (
            release is None
            or release == "0" * 40
            or when is None
            or datetime.fromisoformat(when).utcoffset() is None
        ):
            return None
        result: dict[str, object] = {
            "time": when,
            "level": level,
            "event": event,
            "service_release": release,
        }
        if event == "ai_runtime_failure":
            result.update(
                {
                    "ai_runtime_phase": member(data.get("ai_runtime_phase"), PHASES),
                    "ai_runtime_code": member(data.get("ai_runtime_code"), CODES),
                    "ai_runtime_failure_role": member(
                        data.get("ai_runtime_failure_role"), frozenset({"primary", "cleanup"})
                    ),
                }
            )
        if event == "runtime_error":
            result.update(error_metadata(data))
        if data.get("component") == "telemetry":
            result["component"] = "telemetry"
        outcome = data.get("outcome")
        if isinstance(outcome, str) and outcome in OUTCOMES:
            result["outcome"] = outcome
        duration = data.get("duration_seconds")
        if (
            isinstance(duration, (float, int))
            and not isinstance(duration, bool)
            and math.isfinite(duration)
            and duration >= 0
        ):
            result["duration_seconds"] = duration
        for key, length in (
            ("trace_id", 32),
            ("span_id", 16),
            ("origin_trace_id", 32),
            ("origin_span_id", 16),
        ):
            identifier = data.get(key)
            if (
                isinstance(identifier, str)
                and re.fullmatch("[0-9a-f]{" + str(length) + "}", identifier)
                and identifier != "0" * length
            ):
                result[key] = identifier
        encoded = (
            json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
            + b"\n"
        )
        return Message(encoded, LEVELS[level]) if len(encoded) <= MAX_MESSAGE else None
    except (ValueError, TypeError, RecursionError, OverflowError):
        return None


@dataclass(slots=True)
class Framer:
    pending: bytearray = field(default_factory=bytearray)
    discarding: bool = False
    oversized: int = 0

    def feed(self, data: bytes) -> list[bytes]:
        lines: list[bytes] = []
        for part in data.splitlines(keepends=True):
            complete = part.endswith(b"\n")
            if not self.discarding and len(self.pending) + len(part) <= MAX_LINE:
                self.pending.extend(part)
            else:
                if not self.discarding:
                    self.oversized += 1
                self.pending.clear()
                self.discarding = True
            if complete:
                if not self.discarding:
                    lines.append(bytes(self.pending))
                self.pending.clear()
                self.discarding = False
        return lines


@dataclass(slots=True)
class Counters:
    rejected: int = 0
    dropped: int = 0
    forwarded: int = 0


def docker_command(container_id: str) -> tuple[str, ...]:
    if HEX_ID.fullmatch(container_id) is None or container_id == "0" * 64:
        raise RejectedError("container_id")
    return (
        str(DOCKER),
        "--config",
        str(CONFIG),
        "--host",
        "unix://" + str(SOCKET),
        "logs",
        "--follow",
        "--timestamps",
        "--since",
        "30s",
        "--tail",
        "200",
        "--",
        container_id,
    )


def logger_command(priority: str) -> tuple[str, ...]:
    if priority not in LEVELS.values():
        raise RejectedError("priority")
    return (
        str(LOGGER),
        "--tcp",
        "--server",
        "127.0.0.1",
        "--port",
        "5514",
        "--rfc5424",
        "--tag",
        "studymate-ai-worker",
        "--size",
        "16384",
        "--priority",
        "user." + priority,
    )


def trusted_binary(path: Path, expected: str | None = None) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o022
            or not 0 < info.st_size <= MAX_BINARY
        ):
            raise RejectedError("binary_metadata")
        if expected is not None:
            if HEX_ID.fullmatch(expected) is None:
                raise RejectedError("binary_pin")
            with os.fdopen(os.dup(descriptor), "rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise RejectedError("binary_pin")
    finally:
        os.close(descriptor)


def prepare() -> None:
    if os.geteuid() != 0:
        raise RejectedError("host_identity")
    for path in (STATE, CONFIG):
        path.mkdir(mode=PRIVATE_MODE, exist_ok=True)
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != PRIVATE_MODE
        ):
            raise RejectedError("state_metadata")
    socket_info = SOCKET.stat()
    if (
        next(CONFIG.iterdir(), None) is not None
        or not stat.S_ISSOCK(socket_info.st_mode)
        or socket_info.st_uid != 0
    ):
        raise RejectedError("empty_local_configuration")


def read_source(
    process: subprocess.Popen[bytes],
    output: queue.Queue[Message],
    stop: threading.Event,
    counters: Counters,
) -> None:
    with selectors.DefaultSelector() as selected:
        for pipe in (process.stdout, process.stderr):
            if pipe is None:
                raise RejectedError("missing_pipe")
            selected.register(pipe, selectors.EVENT_READ, Framer())
        while selected.get_map() and not stop.is_set():
            for key, _events in selected.select(SELECT_SECONDS):
                data = os.read(key.fd, CHUNK)
                if not data:
                    selected.unregister(key.fileobj)
                    continue
                framer: object = key.data
                if not isinstance(framer, Framer):
                    raise RejectedError("unexpected_stream_state")
                before = framer.oversized
                lines = framer.feed(data)
                counters.rejected += framer.oversized - before
                for line in lines:
                    message = sanitize(line)
                    if message is None:
                        counters.rejected += 1
                        continue
                    try:
                        output.put_nowait(message)
                    except queue.Full:
                        counters.dropped += 1


def send(message: Message) -> bool:
    try:
        # Fixed root-owned native logger; JSON is stdin, never a shell/argv.
        result = subprocess.run(  # noqa: S603 - fixed trusted native logger; payload only stdin.
            logger_command(message.priority),
            input=message.encoded,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=ENVIRONMENT,
            timeout=SEND_SECONDS,
            check=False,
            close_fds=True,
            start_new_session=True,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def stop_reader(process: subprocess.Popen[bytes]) -> None:
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
    finally:
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()


def relay(container_id: str, stop: threading.Event) -> int:
    # Fixed root-owned docker binary, closed full ID, explicit empty config/local UNIX.
    process = subprocess.Popen(  # noqa: S603 - root-pinned docker/logs only, closed full CID.
        docker_command(container_id),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=ENVIRONMENT,
        close_fds=True,
        start_new_session=True,
    )
    output: queue.Queue[Message] = queue.Queue(maxsize=QUEUE_SIZE)
    counters = Counters()
    failure: list[Literal["source_read_failed"]] = []

    def reader() -> None:
        try:
            read_source(process, output, stop, counters)
        except (OSError, RejectedError):
            failure.append("source_read_failed")

    thread = threading.Thread(target=reader, name="ai-log-read", daemon=True)
    thread.start()
    result = 0
    sender_dropped = 0
    try:
        while not stop.is_set() and (thread.is_alive() or not output.empty()):
            try:
                message = output.get(timeout=SELECT_SECONDS)
            except queue.Empty:
                continue
            if not send(message):
                sender_dropped = 1 + output.qsize()
                result = 75
                break
            counters.forwarded += 1
    finally:
        requested_stop = stop.is_set()
        stop.set()
        thread.join(timeout=1)
        stop_reader(process)
        thread.join(timeout=1)
    if failure or thread.is_alive() or (not requested_stop and process.returncode != 0):
        result = 75
    sys.stdout.write(
        json.dumps(
            {
                "event": "ai_log_relay_stopped",
                "forwarded": counters.forwarded,
                "rejected": counters.rejected,
                "dropped": counters.dropped + sender_dropped,
                "status": result,
            }
        )
        + "\n"
    )
    return result


class ClosedParser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        raise RejectedError("arguments")


def main() -> int:
    parser = ClosedParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--docker-sha256", required=True)
    stop = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda _number, _frame: stop.set())
    try:
        options = parser.parse_args()
        docker_command(options.container_id)
        trusted_binary(DOCKER, options.docker_sha256)
        trusted_binary(LOGGER)
        prepare()
        return relay(options.container_id, stop)
    except Exception:
        # Host boundary fails closed without copying exception text or private input.
        sys.stdout.write(
            '{"event":"ai_log_relay_stopped","reason":"configuration_or_process","status":75}\n'
        )
        return 75


if __name__ == "__main__":
    sys.exit(main())
