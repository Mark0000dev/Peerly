from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from studymate.domain.ai.tasks import AiResult, AiTask, validate_result
from studymate.domain.time import require_aware

MAX_VERSION_LENGTH = 100
DIGEST_BYTES = 32
MAX_ATTEMPTS = 3


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Failure(StrEnum):
    TRANSIENT = "transient"
    INVALID_OUTPUT = "invalid_output"
    INVALID_INPUT = "invalid_input"
    TIMEOUT = "timeout"
    AUTH = "auth_unavailable"
    RATE_LIMIT = "rate_limited"
    ACCOUNT = "account_unavailable"
    STALE_SOURCE = "stale_source"
    EXECUTOR_LOST = "executor_lost"


class LeaseLostError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Versions:
    model: str
    prompt: str = "peerly-ai-v2"
    schema: str = "peerly-ai-v2"
    adapter: str = "codex-subscription"

    def __post_init__(self) -> None:
        if any(
            not value.strip() or len(value) > MAX_VERSION_LENGTH
            for value in (self.model, self.prompt, self.schema, self.adapter)
        ):
            raise ValueError("Explicit bounded executor versions are required")


@dataclass(frozen=True, slots=True)
class AiJob:
    id: UUID
    actor_id: UUID
    task: AiTask = field(repr=False)
    digest: bytes = field(repr=False)
    versions: Versions
    created_at: datetime
    deadline: datetime
    not_before: datetime
    state: JobState = JobState.QUEUED
    attempts: int = 0
    generation: int = 0
    token: UUID | None = None
    result: AiResult | None = field(default=None, repr=False)
    failure: Failure | None = None

    def __post_init__(self) -> None:
        for value in (self.created_at, self.deadline, self.not_before):
            require_aware(value)
        if len(self.digest) != DIGEST_BYTES or self.deadline <= self.created_at:
            raise ValueError("Job digest and deadline are required")
        if not 0 <= self.attempts <= MAX_ATTEMPTS or self.generation < 0:
            raise ValueError("Attempt budget exceeded")
        if (self.state == JobState.SUCCEEDED) != (self.result is not None):
            raise ValueError("Only successful jobs contain results")
        if self.result is not None:
            validate_result(self.task, self.result)

    @property
    def pending(self) -> bool:
        return self.state in {JobState.QUEUED, JobState.RUNNING}

    def cancel(self) -> "AiJob":
        return replace(self, state=JobState.CANCELLED) if self.pending else self

    def claim(self, token: UUID, generation: int, at: datetime) -> "AiJob":
        require_aware(at)
        if self.state != JobState.QUEUED or self.not_before > at:
            raise ValueError("Job is not due")
        if at + timedelta(seconds=1) >= self.deadline:
            return replace(self, state=JobState.EXPIRED)
        return replace(
            self,
            state=JobState.RUNNING,
            token=token,
            generation=generation,
            attempts=self.attempts + 1,
            failure=None,
        )

    def finish(self, result: AiResult, at: datetime) -> "AiJob":
        if self.state != JobState.RUNNING:
            return self
        require_aware(at)
        if at >= self.deadline:
            return replace(self, state=JobState.EXPIRED)
        validate_result(self.task, result)
        return replace(self, state=JobState.SUCCEEDED, result=result)

    def fail(self, failure: Failure, at: datetime, delay: timedelta) -> "AiJob":
        require_aware(at)
        if self.state != JobState.RUNNING:
            return self
        retry = failure in {
            Failure.TRANSIENT,
            Failure.TIMEOUT,
            Failure.INVALID_OUTPUT,
            Failure.RATE_LIMIT,
            Failure.EXECUTOR_LOST,
        }
        budget = 2 if failure == Failure.INVALID_OUTPUT else 3
        if delay < timedelta(0) or delay > timedelta(minutes=5):
            raise ValueError("Retry delay must be bounded")
        if at >= self.deadline:
            state = JobState.EXPIRED
        elif retry and self.attempts < budget and at + delay + timedelta(seconds=1) < self.deadline:
            state = JobState.QUEUED
        else:
            state = JobState.FAILED
        return replace(self, state=state, failure=failure, not_before=at + delay)
