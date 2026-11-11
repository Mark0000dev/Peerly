"""Retained AI business records without current task decoding or executor authority."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.ai.jobs import Failure, JobState
from studymate.domain.ai.tasks import AiKind
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.time import require_aware

OPERATOR_AI_PAGE_SIZE = 50
OPERATOR_AI_MAX_ATTEMPTS = 3
OPERATOR_AI_INPUT_BYTES = 32768
OPERATOR_AI_RESULT_BYTES = 16384
OPERATOR_AI_DIGEST_BYTES = 32


class OperatorAiAttemptOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRANSIENT = "transient"
    INVALID_OUTPUT = "invalid_output"
    INVALID_INPUT = "invalid_input"
    TIMEOUT = "timeout"
    AUTH_UNAVAILABLE = "auth_unavailable"
    RATE_LIMITED = "rate_limited"
    ACCOUNT_UNAVAILABLE = "account_unavailable"
    STALE_SOURCE = "stale_source"
    EXECUTOR_LOST = "executor_lost"


@dataclass(frozen=True, slots=True)
class OperatorAiVersions:
    model: str
    prompt: str
    schema: str
    adapter: str


@dataclass(frozen=True, slots=True)
class OperatorAiJobMetadata:
    id: UUID
    account_id: UUID
    kind: AiKind
    state: JobState
    source_id: UUID
    source_version: int
    created_at: datetime
    deadline: datetime
    not_before: datetime
    attempts_count: int
    failure: Failure | None
    versions: OperatorAiVersions
    origin: OperatorEventOrigin

    def __post_init__(self) -> None:
        for value in (self.created_at, self.deadline, self.not_before):
            require_aware(value)
        if isinstance(self.source_version, bool) or self.source_version < 1:
            raise ValueError("AI inspection requires its actual positive source version")
        if (
            isinstance(self.attempts_count, bool)
            or not 0 <= self.attempts_count <= OPERATOR_AI_MAX_ATTEMPTS
        ):
            raise ValueError("AI inspection requires its actual bounded attempt count")


@dataclass(frozen=True, slots=True)
class OperatorAiAttempt:
    job_id: UUID
    number: int
    started_at: datetime
    ended_at: datetime | None
    outcome: OperatorAiAttemptOutcome | None

    def __post_init__(self) -> None:
        require_aware(self.started_at)
        if self.ended_at is not None:
            require_aware(self.ended_at)
        if isinstance(self.number, bool) or not 1 <= self.number <= OPERATOR_AI_MAX_ATTEMPTS:
            raise ValueError("AI inspection requires its actual bounded attempt number")


@dataclass(frozen=True, slots=True)
class OperatorAiJobDetail:
    job: OperatorAiJobMetadata
    input_digest: bytes = field(repr=False)
    input_json_raw: str = field(repr=False)
    result_json_raw: str | None = field(repr=False)
    attempts_current: tuple[OperatorAiAttempt, ...]

    def __post_init__(self) -> None:
        if len(self.input_digest) != OPERATOR_AI_DIGEST_BYTES:
            raise ValueError("AI inspection requires the actual stored input digest")
        if len(self.input_json_raw.encode("utf-8")) > OPERATOR_AI_INPUT_BYTES or (
            self.result_json_raw is not None
            and len(self.result_json_raw.encode("utf-8")) > OPERATOR_AI_RESULT_BYTES
        ):
            raise ValueError("AI inspection exceeds actual stored business payload bounds")
        if (
            len(self.attempts_current) > OPERATOR_AI_MAX_ATTEMPTS
            or any(row.job_id != self.job.id for row in self.attempts_current)
            or tuple(row.number for row in self.attempts_current)
            != tuple(sorted({row.number for row in self.attempts_current}))
        ):
            raise ValueError("AI inspection attempts differ from the actual bounded job source")
