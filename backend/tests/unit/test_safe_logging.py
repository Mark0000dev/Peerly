import asyncio
import io
import json
import logging
import logging.config
import sys
from threading import Event, get_ident
from uuid import UUID, uuid4

import pytest

import studymate.infrastructure.observability.logging as safe_logging
from studymate.infrastructure.observability.logging import (
    LogEvent,
    SafeBufferedHandler,
    SafeJsonFormatter,
)

PRIVATE = "private-chat-cookie-otp-provider-sql-value"
DURATION = 0.25
STATUS = 503
TRACE = "a" * 32
SPAN = "b" * 16


class UnrenderableMessage:
    def __str__(self) -> str:
        raise AssertionError("Arbitrary log message was rendered")


def test_arbitrary_messages_arguments_and_extra_fields_never_export() -> None:
    record = logging.LogRecord(
        "provider", logging.ERROR, __file__, 1, UnrenderableMessage(), (PRIVATE,), None
    )
    record.stack_info = PRIVATE
    record.private_body = PRIVATE
    record.event = PRIVATE
    record.account_id = PRIVATE
    output = SafeJsonFormatter().format(record)
    assert PRIVATE not in output
    content = json.loads(output)
    assert set(content) == {"time", "level", "event"}
    assert content["event"] == "runtime_log"


def test_sdk_warning_is_identifiable_without_exporting_provider_details() -> None:
    record = logging.LogRecord(
        "opentelemetry.exporter", logging.WARNING, __file__, 1, PRIVATE, (), None
    )
    output = SafeJsonFormatter().format(record)
    assert PRIVATE not in output
    assert json.loads(output)["component"] == "telemetry"


def test_only_typed_identifiers_and_bounded_numeric_metadata_export() -> None:
    account_id, request_id = uuid4(), uuid4()
    record = logging.LogRecord("app", logging.INFO, __file__, 1, PRIVATE, (), None)
    record.event = LogEvent.REQUEST_COMPLETED
    record.request_id = str(request_id)
    record.account_id = account_id
    record.action_id = uuid4()
    record.delivery_id = UUID(int=1)
    record.trace_id = TRACE
    record.span_id = SPAN
    record.duration_seconds = DURATION
    record.status = STATUS
    content = json.loads(SafeJsonFormatter().format(record))
    assert content["request_id"] == str(request_id)
    assert content["account_id"] == str(account_id)
    assert content["status"] == STATUS
    assert content["duration_seconds"] == DURATION
    assert content["trace_id"] == TRACE
    assert content["span_id"] == SPAN
    assert PRIVATE not in json.dumps(content)


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -1, True, PRIVATE])
def test_invalid_metadata_is_dropped(duration: object) -> None:
    record = logging.LogRecord("app", logging.INFO, __file__, 1, PRIVATE, (), None)
    record.duration_seconds = duration
    record.status = True
    record.trace_id = "0" * 32
    record.span_id = PRIVATE
    content = json.loads(SafeJsonFormatter().format(record))
    assert not {"duration_seconds", "status", "trace_id", "span_id"}.intersection(content)


def test_exception_messages_chains_locals_and_source_lines_never_export() -> None:
    try:
        try:
            raise RuntimeError(PRIVATE)
        except RuntimeError as cause:
            raise ValueError(PRIVATE) from cause
    except ValueError:
        record = logging.LogRecord("db", logging.ERROR, __file__, 1, PRIVATE, (), sys.exc_info())
    record.exc_text = PRIVATE
    output = SafeJsonFormatter().format(record)
    content = json.loads(output)
    assert PRIVATE not in output
    assert content["event"] == "runtime_error"
    assert content["stack"]
    assert all(set(frame) == {"file", "function", "line"} for frame in content["stack"])


def test_uncaught_error_hook_uses_the_same_safe_boundary(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.CRITICAL, logger="studymate.runtime")
    safe_logging.log_uncaught_exception(ValueError, ValueError(PRIVATE), None)
    output = SafeJsonFormatter().format(caplog.records[-1])
    assert PRIVATE not in output
    assert json.loads(output)["event"] == "runtime_error"


def test_process_logging_configures_safe_handlers_without_mutating_test_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configurations: list[dict[str, object]] = []
    monkeypatch.setattr(logging.config, "dictConfig", configurations.append)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    safe_logging.configure_logging()
    assert configurations
    assert sys.excepthook is safe_logging.log_uncaught_exception


async def test_actual_process_uncaught_error_is_sanitized_and_still_exits_unsuccessfully() -> None:
    script = (
        "from studymate.infrastructure.observability.logging import configure_logging\n"
        "configure_logging()\n"
        "import logging\n"
        f"logging.getLogger('untrusted').error({PRIVATE!r})\n"
        f"raise ValueError({PRIVATE!r})\n"
    )
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(child.communicate(), timeout=5)
    assert child.returncode == 1
    assert stderr == b""
    assert PRIVATE.encode() not in stdout
    events = [json.loads(line)["event"] for line in stdout.splitlines()]
    assert events == ["runtime_log", "runtime_error"]


def test_stdout_stall_is_bounded_and_never_writes_on_the_caller_thread() -> None:
    caller = get_ident()
    started, release = Event(), Event()

    class SlowStream(io.StringIO):
        def write(self, text: str) -> int:
            assert get_ident() != caller
            started.set()
            assert release.wait(timeout=2)
            return super().write(text)

    stream = SlowStream()
    handler = SafeBufferedHandler(stream, capacity=1)
    record = logging.LogRecord("test", logging.INFO, __file__, 1, PRIVATE, (), None)
    try:
        handler.emit(record)
        assert started.wait(timeout=2)
        handler.emit(record)
        handler.emit(record)
        assert handler.dropped == 1
        assert not release.is_set()
    finally:
        release.set()
        handler.close()
    assert PRIVATE not in stream.getvalue()
    assert stream.getvalue().splitlines()
    handler.emit(record)
    assert handler.dropped > 1


def test_broken_stdout_and_invalid_records_drop_without_recursive_logging() -> None:
    class BrokenStream(io.StringIO):
        def write(self, _text: str) -> int:
            raise OSError(PRIVATE)

    with pytest.raises(ValueError, match="positive"):
        SafeBufferedHandler(capacity=0)
    handler = SafeBufferedHandler(BrokenStream())
    record = logging.LogRecord("test", logging.INFO, __file__, 1, PRIVATE, (), None)
    handler.emit(record)
    record.created = float("nan")
    handler.emit(record)
    handler.close()
    assert handler.dropped > 1
