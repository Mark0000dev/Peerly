"""Closed immutable runtime-failure metadata, with no logging or application imports."""

from dataclasses import dataclass
from enum import StrEnum


class AiRuntimePhase(StrEnum):
    RECEIPT_RECHECK = "receipt_recheck"
    HEARTBEAT = "heartbeat"
    REVOKE = "revoke"
    PHYSICAL_CLEANUP = "physical_cleanup"
    RETIRE = "retire"


class AiRuntimeCode(StrEnum):
    STORAGE_UNAVAILABLE = "storage_unavailable"
    OWNERSHIP_LOST = "ownership_lost"
    RECEIPT_REJECTED = "receipt_rejected"
    PHYSICAL_STOP_UNCERTAIN = "physical_stop_uncertain"
    CREDENTIAL_UNCERTAIN = "credential_uncertain"
    CANCELLED = "cancelled"
    UNEXPECTED = "unexpected"


@dataclass(frozen=True, slots=True)
class AiRuntimeDiagnostic:
    phase: AiRuntimePhase
    code: AiRuntimeCode
    primary: bool

    def __post_init__(self) -> None:
        phase: object = self.phase
        code: object = self.code
        primary: object = self.primary
        if (
            not isinstance(phase, AiRuntimePhase)
            or not isinstance(code, AiRuntimeCode)
            or type(primary) is not bool
        ):
            raise ValueError("AI runtime diagnostics require closed phase/code and actual boolean")
