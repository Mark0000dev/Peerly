"""Closed transaction failure facts; never retain exception objects or private values."""

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from studymate.application.errors import StorageUnavailableError

MAX_CAUSES = 16


class TransactionPhase(StrEnum):
    ENTRY = "entry"
    BODY = "body"
    COMMIT = "commit"


class TransactionOperation(StrEnum):
    NONE = "none"
    CLOCK = "clock"
    IDENTITY = "identity"
    REPLAY = "replay"
    PREPARE = "prepare"
    RUNTIME = "runtime"
    ADMIT = "admit"
    OWNED = "owned"


class TransactionStage(StrEnum):
    NONE = "none"
    IDENTITY_READ = "identity_read"
    CLOCK_READ = "clock_read"
    SOURCE_READ = "source_read"
    CANDIDATES_READ = "candidates_read"
    RUNTIME_LOCK = "runtime_lock"
    RUNTIME_READINESS = "runtime_readiness"
    REPLAY_READ = "replay_read"
    ADMISSION_LOCK = "admission_lock"
    ADMISSION_OBSERVATION = "admission_observation"
    ADMISSION_DECISION = "admission_decision"
    EXPIRY_UPDATE = "expiry_update"
    EXPIRY_EVENT = "expiry_event"
    ADMISSION_WRITE = "admission_write"
    OWNED_LOCK = "owned_lock"
    OWNED_READ = "owned_read"
    OWNED_EVENT = "owned_event"
    TRANSACTION_EXIT = "transaction_exit"


class TransactionCause(StrEnum):
    DEADLINE = "request_deadline"
    POOL = "pool_timeout"
    LOCK = "lock_unavailable"
    CONNECTION = "connection_unavailable"
    DATABASE = "database_unavailable"
    IO = "io_unavailable"
    TIMEOUT = "timeout"
    STORAGE = "storage_unavailable"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class TransactionProgress:
    phase: TransactionPhase = TransactionPhase.ENTRY
    operation: TransactionOperation = TransactionOperation.NONE
    stage: TransactionStage = TransactionStage.NONE


@dataclass(frozen=True, slots=True)
class AiTransactionDiagnostic:
    phase: TransactionPhase
    operation: TransactionOperation
    cause: TransactionCause
    stage: TransactionStage = TransactionStage.NONE
    deadline_expired: bool = False


def _typed_cause(error: BaseException) -> TransactionCause:
    if isinstance(error, PoolTimeoutError):
        return TransactionCause.POOL
    if isinstance(error, DBAPIError):
        if getattr(error.orig, "sqlstate", None) == "55P03":
            return TransactionCause.LOCK
        if error.connection_invalidated:
            return TransactionCause.CONNECTION
    categories: tuple[tuple[type[BaseException], TransactionCause], ...] = (
        (TimeoutError, TransactionCause.TIMEOUT),
        (InterfaceError, TransactionCause.DATABASE),
        (OperationalError, TransactionCause.DATABASE),
        (OSError, TransactionCause.IO),
        (StorageUnavailableError, TransactionCause.STORAGE),
    )
    return next(
        (cause for kind, cause in categories if isinstance(error, kind)), TransactionCause.UNKNOWN
    )


def classify_failure(error: BaseException, *, deadline_expired: bool) -> TransactionCause:
    if deadline_expired:
        return TransactionCause.DEADLINE
    pending = [error]
    seen: set[int] = set()
    evidence: set[TransactionCause] = set()
    while pending and len(seen) < MAX_CAUSES:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        evidence.add(_typed_cause(current))
        if isinstance(current, DBAPIError) and isinstance(current.orig, BaseException):
            pending.append(current.orig)
        # Inspect suppressed context only for fixed typed facts. Never export the
        # chain or change the formatter's general suppressed-context policy.
        pending.extend(
            value
            for value in (current.__cause__, current.__context__)
            if value is not None and not isinstance(value, asyncio.CancelledError)
        )
    priority = (
        TransactionCause.POOL,
        TransactionCause.LOCK,
        TransactionCause.CONNECTION,
        TransactionCause.TIMEOUT,
        TransactionCause.DATABASE,
        TransactionCause.IO,
        TransactionCause.STORAGE,
    )
    return next((cause for cause in priority if cause in evidence), TransactionCause.UNKNOWN)
