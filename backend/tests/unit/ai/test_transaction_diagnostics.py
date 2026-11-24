import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.ai.ports import Admission, AiUnavailableError
from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.domain.ai.jobs import Versions
from studymate.domain.ai.tasks import ClarifyGoal, Source
from studymate.infrastructure.ai import persistence
from studymate.infrastructure.ai.admission_observation import AdmissionObservation
from studymate.infrastructure.ai.admission_slot import AdmissionSlotLock
from studymate.infrastructure.ai.models import AiSlotRecord
from studymate.infrastructure.ai.persistence import SqlAiUnitOfWork
from studymate.infrastructure.ai.transaction_diagnostics import (
    AiTransactionDiagnostic,
    TransactionCause,
    TransactionOperation,
    TransactionPhase,
    TransactionStage,
    classify_failure,
)
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction

CANARY = "PRIVATE_SQL_PARAMS_TOKEN_STUDENT_BODY"
DEFAULT_BUDGET_SECONDS = 2.0


@pytest.mark.parametrize(
    ("cause", "expected"),
    [
        (PoolTimeoutError(CANARY), TransactionCause.POOL),
        (TimeoutError(CANARY), TransactionCause.TIMEOUT),
        (OSError(CANARY), TransactionCause.IO),
        (StorageUnavailableError(CANARY), TransactionCause.STORAGE),
        (ValueError(CANARY), TransactionCause.STORAGE),
    ],
)
def test_suppressed_context_classification_is_typed_not_error_text(
    cause: BaseException,
    expected: TransactionCause,
) -> None:
    outer = StorageUnavailableError(CANARY)
    outer.__context__ = cause
    outer.__suppress_context__ = True
    assert classify_failure(outer, deadline_expired=False) == expected
    assert classify_failure(outer, deadline_expired=True) == TransactionCause.DEADLINE


class LockUnavailableError(Exception):
    sqlstate = "55P03"


def test_driver_attributes_only_and_cycles_are_bounded() -> None:
    driver = LockUnavailableError(CANARY)
    error = OperationalError(CANARY, {"token": CANARY}, driver)
    outer = StorageUnavailableError(CANARY)
    outer.__context__ = error
    error.__context__ = outer
    assert classify_failure(outer, deadline_expired=False) == TransactionCause.LOCK
    outer.__context__ = outer
    assert classify_failure(outer, deadline_expired=False) == TransactionCause.STORAGE


@pytest.mark.parametrize("phase", list(TransactionPhase))
async def test_failure_phase_is_retained_without_exporting_private_exception(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    phase: TransactionPhase,
) -> None:
    @asynccontextmanager
    async def failing(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
        del sessions
        if phase == TransactionPhase.ENTRY:
            raise StorageUnavailableError(CANARY)
        async with AsyncSession() as session:
            yield session
        if phase == TransactionPhase.COMMIT:
            raise StorageUnavailableError(CANARY)

    monkeypatch.setattr(persistence, "open_transaction", failing)
    uow = SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False))

    async def invoke() -> None:
        async with uow.transaction() as transaction:
            if phase == TransactionPhase.BODY:
                transaction.diagnostic_progress.operation = TransactionOperation.ADMIT
                raise StorageUnavailableError(CANARY)

    with (
        caplog.at_level(logging.WARNING, logger="studymate.ai"),
        pytest.raises(AiUnavailableError) as failed,
    ):
        await invoke()
    assert str(failed.value) == ""
    assert failed.value.__suppress_context__
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.exc_info is None
    assert not any(isinstance(value, BaseException) for value in vars(record).values())
    output = SafeJsonFormatter().format(record)
    assert CANARY not in output
    data = json.loads(output)
    assert data["event"] == "ai_transaction_failure"
    assert data["ai_transaction_phase"] == phase.value
    assert data["ai_transaction_cause"] == "storage_unavailable"
    expected = "admit" if phase == TransactionPhase.BODY else "none"
    assert data["ai_transaction_operation"] == expected


async def test_cancellation_is_not_translated_or_reported_as_storage_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    @asynccontextmanager
    async def available(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
        del sessions
        async with AsyncSession() as session:
            yield session

    monkeypatch.setattr(persistence, "open_transaction", available)
    with pytest.raises(asyncio.CancelledError):
        async with SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False)).transaction():
            raise asyncio.CancelledError(CANARY)
    assert not caplog.records


def test_formatter_rejects_untyped_arbitrary_diagnostic_metadata() -> None:
    record = logging.LogRecord("studymate.ai", logging.WARNING, __file__, 1, CANARY, (), None)
    record.ai_transaction_diagnostic = {"phase": CANARY, "cause": CANARY}
    assert CANARY not in SafeJsonFormatter().format(record)
    record.ai_transaction_diagnostic = AiTransactionDiagnostic(
        TransactionPhase.BODY,
        TransactionOperation.RUNTIME,
        TransactionCause.UNKNOWN,
    )
    output = SafeJsonFormatter().format(record)
    assert CANARY not in output
    assert json.loads(output)["ai_transaction_cause"] == "unknown"


@pytest.mark.parametrize("field_name", ["phase", "operation", "cause", "stage", "deadline_expired"])
def test_formatter_rejects_corrupted_typed_diagnostic(field_name: str) -> None:
    diagnostic = AiTransactionDiagnostic(
        TransactionPhase.ENTRY,
        TransactionOperation.NONE,
        TransactionCause.UNKNOWN,
    )
    object.__setattr__(diagnostic, field_name, CANARY)
    record = logging.LogRecord("studymate.ai", logging.WARNING, __file__, 1, CANARY, (), None)
    record.ai_transaction_diagnostic = diagnostic
    output = SafeJsonFormatter().format(record)
    assert CANARY not in output
    assert "ai_transaction_phase" not in json.loads(output)


@pytest.mark.parametrize("commit", [False, True])
async def test_real_default_deadline_retains_commit_uncertainty_without_retry(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, commit: bool
) -> None:
    entered = 0
    commit_was_recorded = False

    @asynccontextmanager
    async def boundary(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
        nonlocal entered, commit_was_recorded
        del sessions
        entered += 1
        async with AsyncSession() as session:
            yield session
            if commit:
                # Unit boundary model: the write may have completed before reply loss.
                # This is not PostgreSQL acceptance or a real durable-write claim.
                commit_was_recorded = True
                await asyncio.sleep(3)

    monkeypatch.setattr(persistence, "open_transaction", boundary)
    uow = SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False))
    assert uow.policy.request_budget_seconds == DEFAULT_BUDGET_SECONDS

    async def invoke() -> None:
        async with uow.transaction() as transaction:
            if not commit:
                transaction.diagnostic_progress.operation = TransactionOperation.ADMIT
                transaction.diagnostic_progress.stage = TransactionStage.ADMISSION_WRITE
                await asyncio.sleep(3)

    with caplog.at_level(logging.WARNING, logger="studymate.ai"), pytest.raises(AiUnavailableError):
        await invoke()
    assert entered == 1
    assert commit_was_recorded is commit
    assert len(caplog.records) == 1
    data = json.loads(SafeJsonFormatter().format(caplog.records[0]))
    assert data["ai_transaction_deadline_expired"] is True
    assert data["ai_transaction_cause"] == "request_deadline"
    assert data["ai_transaction_phase"] == ("commit" if commit else "body")
    assert data["ai_transaction_stage"] == ("transaction_exit" if commit else "admission_write")
    assert data["ai_transaction_stage_semantics"] == "last_entered"


@pytest.mark.parametrize("commit", [False, True])
async def test_external_cancellation_also_during_commit_is_untranslated(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, commit: bool
) -> None:
    cancellation = asyncio.CancelledError(CANARY)

    @asynccontextmanager
    async def available(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
        del sessions
        async with AsyncSession() as session:
            yield session
            if commit:
                raise cancellation

    monkeypatch.setattr(persistence, "open_transaction", available)

    async def invoke() -> None:
        async with SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False)).transaction():
            if not commit:
                raise cancellation

    with pytest.raises(asyncio.CancelledError) as failed:
        await invoke()
    assert failed.value is cancellation
    assert not caplog.records


async def test_programming_error_is_not_translated_or_logged_as_unavailability(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    @asynccontextmanager
    async def available(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
        del sessions
        async with AsyncSession() as session:
            yield session

    monkeypatch.setattr(persistence, "open_transaction", available)
    error = ValueError(CANARY)
    with pytest.raises(ValueError, match=CANARY) as failed:
        async with SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False)).transaction():
            raise error
    assert failed.value is error
    assert not caplog.records


@pytest.mark.parametrize("operation", ["clock", "identity", "runtime", "observation"])
async def test_actual_adapter_failure_labels_last_entered_boundary_and_safe_origin(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, operation: str
) -> None:
    @asynccontextmanager
    async def available(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
        del sessions
        async with AsyncSession() as session:
            yield session

    async def clock(self: SqlIdentityTransaction) -> datetime:
        del self
        raise StorageUnavailableError(CANARY)

    async def identity(session: AsyncSession, digest: bytes) -> IdentitySnapshot | None:
        del session, digest
        raise StorageUnavailableError(CANARY)

    async def runtime(
        session: AsyncSession, remember: AdmissionSlotLock | None = None
    ) -> AiSlotRecord:
        del session, remember
        raise StorageUnavailableError(CANARY)

    async def ensure(session: AsyncSession, remember: AdmissionSlotLock) -> None:
        del session, remember

    async def observation(session: AsyncSession, intent: Admission) -> AdmissionObservation:
        del session, intent
        raise StorageUnavailableError(CANARY)

    monkeypatch.setattr(persistence, "open_transaction", available)
    monkeypatch.setattr(SqlIdentityTransaction, "now", clock)
    monkeypatch.setattr(persistence, "lock_student_identity", identity)
    monkeypatch.setattr(persistence, "acquire_admission_slot", runtime)
    monkeypatch.setattr(persistence, "ensure_admission_slot", ensure)
    monkeypatch.setattr(persistence, "observe_admission", observation)
    origin = ExecutionOrigin(UUID(int=1), UUID(int=2), "a" * 32, "b" * 16)
    monkeypatch.setattr(persistence, "current_origin", lambda: origin)

    async def invoke() -> None:
        async with SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False)).transaction() as tx:
            if operation == "clock":
                await tx.now()
            elif operation == "identity":
                await tx.lock_identity(CANARY.encode())
            elif operation == "runtime":
                await tx.runtime_versions(datetime.now(UTC))
            else:
                intent = Admission(
                    UUID(int=3),
                    ClarifyGoal(Source(UUID(int=4), 1), CANARY),
                    IntentKey("synthetic-key"),
                    b"x" * 32,
                    Versions("model", "prompt", "schema", "adapter"),
                )
                await tx.admit(intent, datetime.now(UTC))

    with caplog.at_level(logging.WARNING, logger="studymate.ai"), pytest.raises(AiUnavailableError):
        await invoke()
    expected = {
        "clock": ("clock", "clock_read"),
        "identity": ("identity", "identity_read"),
        "runtime": ("runtime", "runtime_lock"),
        "observation": ("admit", "admission_observation"),
    }
    assert len(caplog.records) == 1
    output = SafeJsonFormatter().format(caplog.records[0])
    data = json.loads(output)
    assert (data["ai_transaction_operation"], data["ai_transaction_stage"]) == expected[operation]
    assert data["ai_transaction_phase"] == "body"
    assert data["ai_transaction_deadline_expired"] is False
    assert data["request_id"] == str(origin.request_id)
    assert data["trace_id"] == origin.trace_id
    assert CANARY not in output


def test_connection_invalidation_database_categories_and_untyped_unknown_remain_fixed() -> None:
    driver = RuntimeError(CANARY)
    invalid = DBAPIError(CANARY, {"body": CANARY}, driver, connection_invalidated=True)
    assert classify_failure(invalid, deadline_expired=False) == TransactionCause.CONNECTION
    assert (
        classify_failure(InterfaceError(CANARY, None, driver), deadline_expired=False)
        == TransactionCause.DATABASE
    )
    assert (
        classify_failure(OperationalError(CANARY, None, driver), deadline_expired=False)
        == TransactionCause.DATABASE
    )
    assert classify_failure(ValueError(CANARY), deadline_expired=False) == TransactionCause.UNKNOWN
