"""Closed queue transaction facts; no SQL, values, exception objects or durable claims."""

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import AsyncAdaptedQueuePool

from studymate.application.errors import StorageUnavailableError

MAX_CHAIN = 16


class Operation(StrEnum):
    ACTIVATE = "activate"
    MATERIALIZE = "materialize"
    CLAIM = "claim"
    AUTHORIZE = "authorize"
    FINISH = "finish"
    NONE = "none"


class Phase(StrEnum):
    ENTRY = "entry"
    BODY = "body"
    COMMIT = "commit"


class Stage(StrEnum):
    ENTRY = "entry"
    BODY = "body"
    CONSUMER_LOCK = "consumer_lock"
    GLOBAL_PENDING = "global_pending"
    SOURCE_EVENTS = "source_events"
    MESSAGE_OPERATION = "message_operation"
    MESSAGE_CONVERSATION = "message_conversation"
    REQUEST_AUTHORITY = "request_authority"
    RECIPIENT_PENDING = "recipient_pending"
    DELIVERY_FLUSH = "delivery_flush"
    HINT = "hint"
    ACCOUNTS_LOCK = "accounts_lock"
    RELATIONSHIP_LOCK = "relationship_lock"
    DELIVERY_LOCK = "delivery_lock"
    CLOCK = "clock"
    BINDING = "binding"
    LINEAGE = "lineage"
    BLOCK = "block"
    PREFERENCE = "preference"
    EVENT = "event"
    SOURCE = "source"
    EXIT = "transaction_exit"


class Cause(StrEnum):
    POOL = "pool_timeout"
    LOCK = "lock_unavailable"
    CONNECTION = "connection_unavailable"
    DATABASE = "database_unavailable"
    TIMEOUT = "timeout"
    IO = "io_unavailable"
    STORAGE = "storage_unavailable"
    UNKNOWN = "unknown"


def classify(error: BaseException) -> Cause:
    pending = [error]
    seen: set[int] = set()
    evidence: set[Cause] = set()
    while pending and len(seen) < MAX_CHAIN:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, PoolTimeoutError):
            evidence.add(Cause.POOL)
        if isinstance(current, DBAPIError):
            if getattr(current.orig, "sqlstate", None) == "55P03":
                evidence.add(Cause.LOCK)
            if current.connection_invalidated:
                evidence.add(Cause.CONNECTION)
            if isinstance(current.orig, BaseException):
                pending.append(current.orig)
        categories: tuple[tuple[type[BaseException], Cause], ...] = (
            (OperationalError, Cause.DATABASE),
            (InterfaceError, Cause.DATABASE),
            (OSError, Cause.IO),
            (TimeoutError, Cause.TIMEOUT),
            (StorageUnavailableError, Cause.STORAGE),
        )
        evidence.update(cause for kind, cause in categories if isinstance(current, kind))
        # Suppressed chains supply typed facts ONLY. Never format or export their values.
        pending.extend(e for e in (current.__cause__, current.__context__) if e is not None)
    return next((cause for cause in Cause if cause in evidence), Cause.UNKNOWN)


@dataclass(frozen=True, slots=True)
class Diagnostic:
    operation: Operation
    phase: Phase
    stage: Stage
    cause: Cause
    deadline_expired: bool
    connection_acquired: bool
    pool_size: int | None
    pool_checked_out: int | None
    caught_before_exit_ms: int | None
    observed_after_ms: int


@dataclass(slots=True)
class Progress:
    operation: Operation = Operation.NONE
    phase: Phase = Phase.ENTRY
    stage: Stage = Stage.ENTRY
    connection_acquired: bool = False
    pool_size: int | None = None
    pool_checked_out: int | None = None
    caught_before_exit_ms: int | None = None
    started: float = field(default_factory=monotonic, repr=False)

    def began(self, _session: object, _transaction: object, _connection: object) -> None:
        # SQLAlchemy after_begin fires after this session has obtained a connection.
        self.connection_acquired = True

    def sample_pool(self, session: AsyncSession) -> None:
        bound = session.bind
        if isinstance(bound, AsyncEngine) and isinstance(bound.pool, AsyncAdaptedQueuePool):
            self.pool_size = bound.pool.size()
            self.pool_checked_out = bound.pool.checkedout()

    def caught(self, session: AsyncSession) -> None:
        self.caught_before_exit_ms = max(0, int((monotonic() - self.started) * 1000))
        self.sample_pool(session)

    def diagnostic(self, error: BaseException, *, deadline_expired: bool) -> Diagnostic:
        return Diagnostic(
            self.operation,
            self.phase,
            self.stage,
            classify(error),
            deadline_expired,
            self.connection_acquired,
            self.pool_size,
            self.pool_checked_out,
            self.caught_before_exit_ms,
            max(0, int((monotonic() - self.started) * 1000)),
        )


def metadata(value: object) -> dict[str, str | int | bool | None]:
    if type(value) is not Diagnostic:
        return {}
    operation: object = value.operation
    phase: object = value.phase
    stage: object = value.stage
    cause: object = value.cause
    expired: object = value.deadline_expired
    acquired: object = value.connection_acquired
    if (
        type(operation) is not Operation
        or type(phase) is not Phase
        or type(stage) is not Stage
        or type(cause) is not Cause
        or type(expired) is not bool
        or type(acquired) is not bool
    ):
        return {}
    numbers = (
        value.pool_size,
        value.pool_checked_out,
        value.caught_before_exit_ms,
        value.observed_after_ms,
    )
    if any(
        number is not None and (type(number) is not int or not 0 <= number < 2**63)
        for number in numbers
    ):
        return {}
    return {
        "notification_operation": value.operation.value,
        "notification_phase": value.phase.value,
        "notification_stage": value.stage.value,
        "notification_cause": value.cause.value,
        "notification_deadline_expired": value.deadline_expired,
        "notification_connection_acquired": value.connection_acquired,
        "notification_pool_size": value.pool_size,
        "notification_pool_checked_out": value.pool_checked_out,
        "notification_caught_before_exit_ms": value.caught_before_exit_ms,
        "notification_observed_after_ms": value.observed_after_ms,
        "notification_stage_semantics": "last_entered",
    }


def report(progress: Progress, error: BaseException, *, deadline_expired: bool) -> None:
    logging.getLogger("studymate.student_notifications").warning(
        "Student notification transaction unavailable",
        extra={
            "event": "student_notification_transaction_failure",
            "student_notification_diagnostic": progress.diagnostic(
                error, deadline_expired=deadline_expired
            ),
        },
    )
