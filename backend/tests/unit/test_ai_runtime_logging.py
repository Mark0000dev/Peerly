"""Closed AI failure metadata survives sanitization; provider/SQL text never does."""

import json
import logging
from dataclasses import dataclass

import pytest

from studymate.infrastructure.ai.runtime.diagnostics import (
    AiRuntimeCode,
    AiRuntimeDiagnostic,
    AiRuntimePhase,
)
from studymate.infrastructure.observability.logging import LogEvent, SafeJsonFormatter

PRIVATE = "private-sql-cookie-model-auth-and-message-value"


@pytest.mark.parametrize("primary", [True, False])
@pytest.mark.parametrize("phase", list(AiRuntimePhase))
@pytest.mark.parametrize("code", list(AiRuntimeCode))
def test_only_actual_closed_packet_exports(
    primary: bool, phase: AiRuntimePhase, code: AiRuntimeCode
) -> None:
    record = logging.LogRecord("studymate.ai", logging.ERROR, __file__, 1, PRIVATE, (), None)
    record.event = LogEvent.AI_RUNTIME_FAILURE
    record.ai_runtime_diagnostic = AiRuntimeDiagnostic(phase, code, primary)
    record.exception_class = PRIVATE
    output = SafeJsonFormatter().format(record)
    content = json.loads(output)
    assert PRIVATE not in output
    assert set(content) == {
        "time",
        "level",
        "event",
        "ai_runtime_phase",
        "ai_runtime_code",
        "ai_runtime_failure_role",
    }
    assert content["event"] == "ai_runtime_failure"
    assert content["ai_runtime_phase"] == phase.value
    assert content["ai_runtime_code"] == code.value
    assert content["ai_runtime_failure_role"] == ("primary" if primary else "cleanup")


@dataclass(frozen=True, slots=True)
class UntrustedPacket:
    phase: str = PRIVATE
    code: str = PRIVATE
    primary: bool = True


@pytest.mark.parametrize("packet", [None, PRIVATE, {"code": PRIVATE}, UntrustedPacket()])
def test_structurally_similar_or_arbitrary_packet_does_not_export(packet: object) -> None:
    record = logging.LogRecord("provider", logging.ERROR, __file__, 1, PRIVATE, (), None)
    record.ai_runtime_diagnostic = packet
    output = SafeJsonFormatter().format(record)
    assert PRIVATE not in output
    assert set(json.loads(output)) == {"time", "level", "event"}


@pytest.mark.parametrize("field", ["phase", "code", "primary"])
def test_even_forged_typed_packet_cannot_export_unallowlisted_fields(field: str) -> None:
    packet = AiRuntimeDiagnostic(AiRuntimePhase.HEARTBEAT, AiRuntimeCode.STORAGE_UNAVAILABLE, True)
    # Defensive boundary proof: bypass the constructor as an untrusted log producer could.
    object.__setattr__(packet, field, PRIVATE)
    record = logging.LogRecord("provider", logging.ERROR, __file__, 1, PRIVATE, (), None)
    record.ai_runtime_diagnostic = packet
    output = SafeJsonFormatter().format(record)
    assert PRIVATE not in output
    assert set(json.loads(output)) == {"time", "level", "event"}
