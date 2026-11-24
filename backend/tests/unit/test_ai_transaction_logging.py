"""Actual formatter/handler allowlist rejects private values and forged enum objects."""

import io
import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import pytest

from studymate.infrastructure.ai.transaction_diagnostics import (
    AiTransactionDiagnostic,
    TransactionCause,
    TransactionOperation,
    TransactionPhase,
    TransactionStage,
)
from studymate.infrastructure.observability.logging import (
    LogEvent,
    SafeBufferedHandler,
    SafeJsonFormatter,
)

PRIVATE = "PRIVATE_SQL_PARAMS_COOKIE_OTP_TOKEN_STUDENT_TEXT"


class Unrenderable:
    def __str__(self) -> str:
        raise AssertionError("Private log producer value must never be rendered")


def packet() -> AiTransactionDiagnostic:
    return AiTransactionDiagnostic(
        TransactionPhase.COMMIT,
        TransactionOperation.NONE,
        TransactionCause.DEADLINE,
        TransactionStage.TRANSACTION_EXIT,
        True,
    )


def record() -> logging.LogRecord:
    value = logging.LogRecord(
        "studymate.ai", logging.WARNING, __file__, 1, Unrenderable(), (PRIVATE,), None
    )
    value.event = LogEvent.AI_TRANSACTION_FAILURE
    value.sql = PRIVATE
    value.params = {"cookie": PRIVATE}
    value.exc_text = PRIVATE
    value.stack_info = PRIVATE
    return value


def test_actual_buffered_handler_writes_only_closed_diagnostic_and_correlation() -> None:
    value = record()
    value.ai_transaction_diagnostic = packet()
    value.request_id = UUID(int=1)
    value.action_id = UUID(int=2)
    value.trace_id = "a" * 32
    value.span_id = "b" * 16
    stream = io.StringIO()
    handler = SafeBufferedHandler(stream)
    try:
        handler.emit(value)
    finally:
        handler.close()
    output = stream.getvalue()
    assert PRIVATE not in output
    data = json.loads(output)
    assert data["event"] == "ai_transaction_failure"
    assert data["ai_transaction_phase"] == "commit"
    assert data["ai_transaction_operation"] == "none"
    assert data["ai_transaction_stage"] == "transaction_exit"
    assert data["ai_transaction_cause"] == "request_deadline"
    assert data["ai_transaction_deadline_expired"] is True
    assert data["ai_transaction_stage_semantics"] == "last_entered"
    assert data["request_id"] == str(UUID(int=1))
    assert data["action_id"] == str(UUID(int=2))
    assert data["trace_id"] == "a" * 32
    assert data["span_id"] == "b" * 16
    assert "stack" not in data
    assert "error_type" not in data


@dataclass(frozen=True, slots=True)
class StructurallySimilar:
    phase: str = PRIVATE
    operation: str = PRIVATE
    cause: str = PRIVATE


@pytest.mark.parametrize("untrusted", [None, PRIVATE, {"phase": PRIVATE}, StructurallySimilar()])
def test_arbitrary_packets_and_direct_extra_fields_are_not_exported(untrusted: object) -> None:
    value = record()
    value.ai_transaction_diagnostic = untrusted
    value.ai_transaction_phase = PRIVATE
    value.ai_transaction_deadline_expired = PRIVATE
    data = SafeJsonFormatter().format(value)
    assert PRIVATE not in data
    assert set(json.loads(data)) == {"time", "level", "event"}


@pytest.mark.parametrize(
    ("field", "member"),
    [
        ("phase", TransactionPhase.BODY),
        ("operation", TransactionOperation.ADMIT),
        ("cause", TransactionCause.LOCK),
        ("stage", TransactionStage.ADMISSION_WRITE),
    ],
)
def test_forged_instances_of_actual_enum_class_are_rejected(field: str, member: StrEnum) -> None:
    forged = str.__new__(type(member), member.value)
    object.__setattr__(forged, "_name_", member.name)
    object.__setattr__(forged, "_value_", PRIVATE)
    assert isinstance(forged, type(member))
    assert forged.value == PRIVATE
    diagnostic = packet()
    object.__setattr__(diagnostic, field, forged)
    value = record()
    value.ai_transaction_diagnostic = diagnostic
    output = SafeJsonFormatter().format(value)
    assert PRIVATE not in output
    assert set(json.loads(output)) == {"time", "level", "event"}


@pytest.mark.parametrize("invalid", [0, 1, PRIVATE, None])
def test_deadline_flag_must_be_actual_bool(invalid: object) -> None:
    diagnostic = packet()
    object.__setattr__(diagnostic, "deadline_expired", invalid)
    value = record()
    value.ai_transaction_diagnostic = diagnostic
    output = SafeJsonFormatter().format(value)
    assert PRIVATE not in output
    assert "ai_transaction_phase" not in json.loads(output)


@pytest.mark.parametrize("phase", list(TransactionPhase))
@pytest.mark.parametrize("expired", [False, True])
def test_closed_phase_and_actual_boolean_survive(phase: TransactionPhase, expired: bool) -> None:
    value = record()
    value.ai_transaction_diagnostic = AiTransactionDiagnostic(
        phase,
        TransactionOperation.CLOCK,
        TransactionCause.TIMEOUT,
        TransactionStage.CLOCK_READ,
        expired,
    )
    data = json.loads(SafeJsonFormatter().format(value))
    assert data["ai_transaction_phase"] == phase.value
    assert data["ai_transaction_deadline_expired"] is expired


def test_existing_formatter_metadata_is_identical_with_diagnostic_fields_removed() -> None:
    value = record()
    value.event = LogEvent.REQUEST_COMPLETED
    value.request_id = UUID(int=3)
    value.account_id = UUID(int=4)
    value.status = 503
    value.duration_seconds = 2.0
    value.trace_id = "c" * 32
    value.outcome = "storage_unavailable"
    formatter = SafeJsonFormatter(release="a" * 40)
    before = json.loads(formatter.format(value))
    value.ai_transaction_diagnostic = packet()
    after = json.loads(formatter.format(value))
    assert {k: v for k, v in after.items() if not k.startswith("ai_transaction_")} == before
    assert after["event"] == "request_completed"
    assert after["service_release"] == "a" * 40
    assert PRIVATE not in formatter.format(value)
