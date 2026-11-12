import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.ai.ports import AiUnavailableError
from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.ai import persistence
from studymate.infrastructure.ai.persistence import SqlAiUnitOfWork
from studymate.infrastructure.ai.transaction_diagnostics import (
    AiTransactionDiagnostic,
    TransactionCause,
    TransactionOperation,
    TransactionPhase,
    classify_failure,
)
from studymate.infrastructure.observability.logging import SafeJsonFormatter

CANARY = "PRIVATE_SQL_PARAMS_TOKEN_STUDENT_BODY"


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


@pytest.mark.parametrize("field_name", ["phase", "operation", "cause"])
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
