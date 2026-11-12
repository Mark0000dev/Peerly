"""Pure/synthetic fixtures only; never start Docker/logger/network or read live logs."""

import json
import os
import queue
import subprocess
import threading
from unittest.mock import Mock, patch

import pytest
from deployment.observability.log_relay import ai_log_relay as relay

PREFIX = b"2026-11-12T10:00:00.123456789Z "
RELEASE = "a" * 40


def line(**changes: object) -> bytes:
    data: dict[str, object] = {
        "time": "2026-11-12T10:00:00+00:00",
        "event": "runtime_log",
        "level": "INFO",
        "service_release": RELEASE,
    }
    data.update(changes)
    return PREFIX + json.dumps(data).encode() + b"\n"


def test_preserves_actual_producer_release_and_removes_all_raw_private_fields() -> None:
    sentinel = "PRIVATE_TOKEN"
    result = relay.sanitize(
        line(
            message="PRIVATE_PROMPT",
            stderr="PRIVATE_AUTH",
            result="PRIVATE_RESULT",
            token=sentinel,
            account_id="PRIVATE_ID",
        )
    )
    assert result is not None
    assert json.loads(result.encoded) == {
        "time": "2026-11-12T10:00:00+00:00",
        "event": "runtime_log",
        "level": "INFO",
        "service_release": RELEASE,
    }
    assert b"PRIVATE" not in result.encoded
    assert result.priority == "info"


@pytest.mark.parametrize(
    "changes",
    [
        {"service_release": None},
        {"service_release": "0" * 40},
        {"service_release": "invented"},
        {"time": "PRIVATE_TIME"},
        {"event": "PRIVATE_MESSAGE"},
        {"level": "PRIVATE_LEVEL"},
        {"event": "request_completed"},
    ],
)
def test_invalid_or_unowned_source_metadata_dropped_without_fallback(
    changes: dict[str, object],
) -> None:
    assert relay.sanitize(line(**changes)) is None


def test_missing_release_duplicate_keys_raw_stderr_and_nonfinite_are_dropped() -> None:
    assert (
        relay.sanitize(
            PREFIX + b'{"event":"runtime_log","level":"INFO","time":"2026-11-12T10:00:00+00:00"}'
        )
        is None
    )
    assert relay.sanitize(line()[:-2] + b',"event":"runtime_log"}\n') is None
    assert relay.sanitize(PREFIX + b"PRIVATE_RAW_NATIVE_STDERR") is None
    assert relay.sanitize(line(duration_seconds=float("nan"))) is None
    assert relay.sanitize(b"PRIVATE_NO_DOCKER_TIMESTAMP") is None


def test_actual_closed_ai_failure_and_technical_stack_without_locals_or_error_text() -> None:
    result = relay.sanitize(
        line(
            event="ai_runtime_failure",
            level="ERROR",
            ai_runtime_phase="heartbeat",
            ai_runtime_code="ownership_lost",
            ai_runtime_failure_role="primary",
            message="PRIVATE",
        )
    )
    assert result is not None
    assert json.loads(result.encoded)["ai_runtime_code"] == "ownership_lost"
    assert result.priority == "err"
    assert (
        relay.sanitize(
            line(
                event="ai_runtime_failure",
                ai_runtime_phase="PRIVATE",
                ai_runtime_code="unexpected",
                ai_runtime_failure_role="primary",
            )
        )
        is None
    )
    error = relay.sanitize(
        line(
            event="runtime_error",
            error_type="OperationalError",
            database_error_code="08006",
            error_message="PRIVATE",
            stack=[
                {"file": "factory.py", "function": "_serve", "line": 10, "locals": "PRIVATE"},
                {"file": "/private/auth.json", "function": "PRIVATE", "line": 1},
            ],
        )
    )
    assert error is not None
    payload = json.loads(error.encoded)
    assert payload["stack"] == [{"file": "factory.py", "function": "_serve", "line": 10}]
    assert b"PRIVATE" not in error.encoded
    assert b"auth.json" not in error.encoded


def test_framer_bounds_oversized_split_lines_and_recovers_at_next_newline() -> None:
    framer = relay.Framer()
    assert framer.feed(b"x" * relay.MAX_LINE) == []
    assert framer.feed(b"y") == []
    assert len(framer.pending) == 0
    assert framer.oversized == 1
    assert framer.feed(b"\n" + line()) == [line()]
    assert relay.sanitize(b"x" * (relay.MAX_LINE + 1)) is None


def test_source_is_one_closed_container_local_empty_config_and_no_fallback() -> None:
    command = relay.docker_command("a" * 64)
    assert command == (
        "/usr/bin/docker",
        "--config",
        "/var/lib/peerly-ai-log-relay/docker-config",
        "--host",
        "unix:///var/run/docker.sock",
        "logs",
        "--follow",
        "--timestamps",
        "--since",
        "30s",
        "--tail",
        "200",
        "--",
        "a" * 64,
    )
    for invalid in ("all", "--all", "worker", "0" * 64, "a" * 63, "tcp://host:2375"):
        with pytest.raises(relay.RejectedError, match="container_id"):
            relay.docker_command(invalid)
    assert "DOCKER_HOST" not in relay.ENVIRONMENT
    assert "DOCKER_CONTEXT" not in relay.ENVIRONMENT
    assert "OPENAI_API_KEY" not in relay.ENVIRONMENT


def test_native_logger_is_fixed_tcp_rfc5424_no_octet_counting_or_raw_argv_payload() -> None:
    command = relay.logger_command("err")
    assert command == (
        "/usr/bin/logger",
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
        "user.err",
    )
    with pytest.raises(relay.RejectedError, match="priority"):
        relay.logger_command("PRIVATE")
    result = relay.sanitize(line())
    assert result is not None
    with patch.object(
        subprocess, "run", return_value=subprocess.CompletedProcess(command, 0)
    ) as run:
        assert relay.send(result)
    assert run.call_args.kwargs["input"] == result.encoded
    assert run.call_args.kwargs["timeout"] == relay.SEND_SECONDS
    assert run.call_args.kwargs["stderr"] == subprocess.DEVNULL
    assert result.encoded.decode().strip() not in command


def test_backpressure_storage_is_finite_and_transport_failure_does_not_log_raw_error() -> None:
    output: queue.Queue[relay.Message] = queue.Queue(maxsize=relay.QUEUE_SIZE)
    result = relay.sanitize(line())
    assert result is not None
    for _ in range(relay.QUEUE_SIZE):
        output.put_nowait(result)
    with pytest.raises(queue.Full):
        output.put_nowait(result)
    with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("PRIVATE", 2)):
        assert not relay.send(result)


def test_actual_pipe_drain_drops_full_queue_and_private_stderr_without_blocking() -> None:
    output: queue.Queue[relay.Message] = queue.Queue(maxsize=relay.QUEUE_SIZE)
    message = relay.sanitize(line())
    assert message is not None
    for _ in range(relay.QUEUE_SIZE):
        output.put_nowait(message)
    out_read, out_write = os.pipe()
    err_read, err_write = os.pipe()
    try:
        os.write(out_write, line())
        os.write(err_write, b"PRIVATE_NATIVE_STDERR\n")
    finally:
        os.close(out_write)
        os.close(err_write)
    process = Mock(spec=subprocess.Popen)
    counts = relay.Counters()
    with os.fdopen(out_read, "rb") as stdout, os.fdopen(err_read, "rb") as stderr:
        process.stdout = stdout
        process.stderr = stderr
        relay.read_source(process, output, threading.Event(), counts)
    assert counts.rejected == 1
    assert counts.dropped == 1
    assert output.qsize() == relay.QUEUE_SIZE
