"""Source allowlist: arbitrary log messages, arguments and exception text never export."""

import json
import logging
import logging.config
import math
import re
import sys
from collections import deque
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from traceback import walk_tb
from types import TracebackType
from typing import TextIO
from uuid import UUID

from sqlalchemy.exc import DBAPIError

from studymate.application.ports.http_observer import HttpObservation
from studymate.infrastructure.ai.runtime.diagnostics import (
    AiRuntimeCode,
    AiRuntimeDiagnostic,
    AiRuntimePhase,
)
from studymate.infrastructure.ai.transaction_diagnostics import (
    AiTransactionDiagnostic,
    TransactionCause,
    TransactionOperation,
    TransactionPhase,
)

MAX_STACK_FRAMES = 20
MAX_APPLICATION_FRAMES = 10
MAX_ERROR_CHAIN = 16
ERROR_TYPE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
SQLSTATE = re.compile(r"[0-9A-Z]{5}")
SERVICE_RELEASE = re.compile(r"[0-9a-f]{40}")
HTTP_STATUS_MIN = 100
HTTP_STATUS_MAX = 599
LOG_QUEUE_CAPACITY = 1024
LOG_SHUTDOWN_SECONDS = 0.5
LOG_IDLE_SECONDS = 0.1


class LogEvent(StrEnum):
    REQUEST_COMPLETED = "request_completed"
    WORKER_STEP = "worker_step"
    WORKER_STOPPED = "worker_stopped"
    WORKER_STORAGE_UNAVAILABLE = "worker_storage_unavailable"
    AI_RUNTIME_FAILURE = "ai_runtime_failure"
    AI_TRANSACTION_FAILURE = "ai_transaction_failure"
    RUNTIME_ERROR = "runtime_error"
    RUNTIME_LOG = "runtime_log"


def _uuid(record: logging.LogRecord, name: str) -> str | None:
    value: object = getattr(record, name, None)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        try:
            return str(UUID(value))
        except ValueError:
            return None
    return None


def _hex(record: logging.LogRecord, name: str, length: int) -> str | None:
    value: object = getattr(record, name, None)
    if (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
        and any(character != "0" for character in value)
    ):
        return value
    return None


def _error_metadata(error: BaseException) -> dict[str, str]:
    """Public DBAPI attributes only; never inspect args, SQL, params or error text."""
    pending = deque([error])
    seen: set[int] = set()
    content: dict[str, str] = {}
    while pending and len(seen) < MAX_ERROR_CHAIN:
        current = pending.popleft()
        if id(current) in seen:
            continue
        seen.add(id(current))
        name = type(current).__name__
        if ERROR_TYPE.fullmatch(name):
            content["error_type"] = name
        if isinstance(current, DBAPIError):
            value: object = getattr(current.orig, "sqlstate", None)
            if isinstance(value, str) and SQLSTATE.fullmatch(value):
                content["database_error_code"] = value
            if isinstance(current.orig, BaseException):
                pending.append(current.orig)
        cause = current.__cause__
        if cause is None and not current.__suppress_context__:
            cause = current.__context__
        if cause is not None:
            pending.append(cause)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions[:MAX_ERROR_CHAIN])
    return content


def _safe_stack(traceback: TracebackType | None) -> list[dict[str, str | int]]:
    """Keep application callers even when driver internals exceed the frame cap."""
    application: deque[tuple[int, dict[str, str | int]]] = deque(maxlen=MAX_APPLICATION_FRAMES)
    tail: deque[tuple[int, dict[str, str | int]]] = deque(maxlen=MAX_STACK_FRAMES)
    for index, (frame, line) in enumerate(walk_tb(traceback)):
        value: dict[str, str | int] = {
            "file": Path(frame.f_code.co_filename).name,
            "function": frame.f_code.co_name,
            "line": line,
        }
        tail.append((index, value))
        module: object = frame.f_globals.get("__name__")
        if isinstance(module, str) and module.startswith("studymate."):
            application.append((index, value))
    selected = dict(application)
    for index, value in reversed(tail):
        if len(selected) >= MAX_STACK_FRAMES:
            break
        selected.setdefault(index, value)
    return [selected[index] for index in sorted(selected)]


def _ai_runtime_metadata(record: logging.LogRecord) -> dict[str, str]:
    diagnostic: object = getattr(record, "ai_runtime_diagnostic", None)
    if not isinstance(diagnostic, AiRuntimeDiagnostic):
        return {}
    phase: object = getattr(diagnostic, "phase", None)
    code: object = getattr(diagnostic, "code", None)
    primary: object = getattr(diagnostic, "primary", None)
    if (
        not isinstance(phase, AiRuntimePhase)
        or not isinstance(code, AiRuntimeCode)
        or type(primary) is not bool
    ):
        return {}
    return {
        "ai_runtime_phase": phase.value,
        "ai_runtime_code": code.value,
        "ai_runtime_failure_role": "primary" if primary is True else "cleanup",
    }


def _ai_transaction_metadata(record: logging.LogRecord) -> dict[str, str]:
    diagnostic: object = getattr(record, "ai_transaction_diagnostic", None)
    if not isinstance(diagnostic, AiTransactionDiagnostic):
        return {}
    phase: object = getattr(diagnostic, "phase", None)
    operation: object = getattr(diagnostic, "operation", None)
    cause: object = getattr(diagnostic, "cause", None)
    if (
        not isinstance(phase, TransactionPhase)
        or not isinstance(operation, TransactionOperation)
        or not isinstance(cause, TransactionCause)
    ):
        return {}
    return {
        "ai_transaction_phase": phase.value,
        "ai_transaction_operation": operation.value,
        "ai_transaction_cause": cause.value,
    }


def validated_service_release(value: object) -> str | None:
    if (
        isinstance(value, str)
        and SERVICE_RELEASE.fullmatch(value) is not None
        and value != "0" * 40
    ):
        return value
    return None


class SafeJsonFormatter(logging.Formatter):
    def __init__(self, *, release: str | None = None) -> None:
        super().__init__()
        self._service_release = validated_service_release(release)

    def bind_release(self, release: str | None) -> None:
        self._service_release = validated_service_release(release)

    def format(self, record: logging.LogRecord) -> str:
        supplied: object = getattr(record, "event", None)
        event = (
            supplied if isinstance(supplied, str) and supplied in LogEvent else LogEvent.RUNTIME_LOG
        )
        content: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": {
                logging.DEBUG: "DEBUG",
                logging.INFO: "INFO",
                logging.WARNING: "WARNING",
                logging.ERROR: "ERROR",
                logging.CRITICAL: "CRITICAL",
            }.get(record.levelno, "INFO"),
            "event": event,
        }
        if self._service_release is not None:
            content["service_release"] = self._service_release
        content.update(_ai_runtime_metadata(record))
        content.update(_ai_transaction_metadata(record))
        if record.name.startswith("opentelemetry."):
            content["component"] = "telemetry"
        observation: object = getattr(record, "observation", None)
        if isinstance(observation, HttpObservation):
            content["method"] = observation.method
            content["route"] = observation.route
        for name in (
            "request_id",
            "action_id",
            "account_id",
            "delivery_id",
            "origin_request_id",
            "upload_id",
            "attempt_id",
        ):
            identifier = _uuid(record, name)
            if identifier is not None:
                content[name] = identifier
        for name, length in (
            ("trace_id", 32),
            ("span_id", 16),
            ("origin_trace_id", 32),
            ("origin_span_id", 16),
        ):
            identifier = _hex(record, name, length)
            if identifier is not None:
                content[name] = identifier
        outcome: object = getattr(record, "outcome", None)
        if isinstance(outcome, str) and outcome in {
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
        }:
            content["outcome"] = outcome
        worker: object = getattr(record, "worker", None)
        if isinstance(worker, str) and worker in (
            "photo",
            "cleanup",
            "request_expiry",
            "change_publication",
            "change_retention",
        ):
            content["worker"] = worker
        duration: object = getattr(record, "duration_seconds", None)
        if (
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and math.isfinite(duration)
            and duration >= 0
        ):
            content["duration_seconds"] = duration
        status: object = getattr(record, "status", None)
        if (
            isinstance(status, int)
            and not isinstance(status, bool)
            and HTTP_STATUS_MIN <= status <= HTTP_STATUS_MAX
        ):
            content["status"] = status
        if record.exc_info is not None and record.exc_info[1] is not None:
            content["event"] = LogEvent.RUNTIME_ERROR
            content.update(_error_metadata(record.exc_info[1]))
            content["stack"] = _safe_stack(record.exc_info[2])
        return json.dumps(content, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


class SafeBufferedHandler(logging.Handler):
    """Only sanitized JSON enters a bounded queue; stdout cannot hold the event loop."""

    def __init__(self, stream: TextIO | None = None, capacity: int = LOG_QUEUE_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("Log queue capacity must be positive")
        super().__init__()
        self.setFormatter(SafeJsonFormatter())
        self._stream = stream if stream is not None else sys.stdout
        self._queue: Queue[str] = Queue(maxsize=capacity)
        self._stop = Event()
        self._drops = 0
        self._counter_lock = Lock()
        self._writer = Thread(target=self._write, name="studymate-log-writer", daemon=True)
        self._writer.start()

    @property
    def dropped(self) -> int:
        with self._counter_lock:
            return self._drops

    def _drop(self) -> None:
        with self._counter_lock:
            self._drops += 1

    def emit(self, record: logging.LogRecord) -> None:
        if self._stop.is_set():
            self._drop()
            return
        try:
            prepared = self.format(record)
        except (TypeError, ValueError, OverflowError):
            self._drop()
            return
        try:
            self._queue.put_nowait(prepared)
        except Full:
            self._drop()

    def _write(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                line = self._queue.get(timeout=LOG_IDLE_SECONDS)
            except Empty:
                continue
            try:
                self._stream.write(line + "\n")
                self._stream.flush()
            except (OSError, ValueError):
                self._drop()
            finally:
                self._queue.task_done()

    def close(self) -> None:
        self._stop.set()
        self._writer.join(timeout=LOG_SHUTDOWN_SECONDS)
        super().close()


def bind_log_release(release: str | None) -> None:
    """Bind this process's validated settings to owned formatters before SDK startup.

    Do not install handlers, mutate log levels or trust caller/record metadata.
    Separate API/worker processes receive their own configuration, including AI.
    """
    loggers = (
        logging.getLogger(),
        *(
            logging.getLogger(name)
            for name in (
                "uvicorn",
                "uvicorn.error",
                "uvicorn.access",
                "studymate",
                "opentelemetry",
            )
        ),
    )
    seen: set[int] = set()
    for logger in loggers:
        for handler in tuple(logger.handlers):
            formatter = handler.formatter
            if isinstance(formatter, SafeJsonFormatter) and id(formatter) not in seen:
                formatter.bind_release(release)
                seen.add(id(formatter))


def logging_configuration() -> dict[str, object]:
    return {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "safe": {"()": "studymate.infrastructure.observability.logging.SafeJsonFormatter"}
        },
        "handlers": {
            "stdout": {
                "class": "studymate.infrastructure.observability.logging.SafeBufferedHandler",
                "formatter": "safe",
            }
        },
        "root": {"level": "INFO", "handlers": ["stdout"]},
        "loggers": {
            "uvicorn": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": [], "level": "INFO", "propagate": True},
            "uvicorn.access": {"handlers": [], "level": "CRITICAL", "propagate": False},
            "studymate": {"handlers": [], "level": "INFO", "propagate": True},
            "opentelemetry": {"handlers": [], "level": "INFO", "propagate": True},
        },
    }


def log_uncaught_exception(
    kind: type[BaseException], value: BaseException, traceback: TracebackType | None
) -> None:
    logging.getLogger("studymate.runtime").critical(
        LogEvent.RUNTIME_ERROR,
        exc_info=(kind, value, traceback),
        extra={"event": LogEvent.RUNTIME_ERROR},
    )


def configure_logging() -> None:
    logging.config.dictConfig(logging_configuration())
    sys.excepthook = log_uncaught_exception
