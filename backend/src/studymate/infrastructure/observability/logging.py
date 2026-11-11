"""Source allowlist: arbitrary log messages, arguments and exception text never export."""

import json
import logging
import logging.config
import math
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

from studymate.application.ports.http_observer import HttpObservation
from studymate.infrastructure.ai.runtime.diagnostics import (
    AiRuntimeCode,
    AiRuntimeDiagnostic,
    AiRuntimePhase,
)

MAX_STACK_FRAMES = 20
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


class SafeJsonFormatter(logging.Formatter):
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
        content.update(_ai_runtime_metadata(record))
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
            content["stack"] = [
                {
                    "file": Path(frame.f_code.co_filename).name,
                    "function": frame.f_code.co_name,
                    "line": line,
                }
                for frame, line in deque(walk_tb(record.exc_info[2]), maxlen=MAX_STACK_FRAMES)
            ]
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
