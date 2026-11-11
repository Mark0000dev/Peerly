from dataclasses import dataclass
from datetime import timedelta

from studymate.application.ai.ports import AiExecutorError
from studymate.domain.ai.jobs import AiJob

MAX_QUEUE = 100
MAX_STUDENT_OUTSTANDING = 2
MAX_BUCKET = 5
MAX_ADMISSION_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class AdmissionPolicy:
    """Configurable within database safety ceilings; larger limits require reviewed DDL."""

    queue_limit: int = MAX_QUEUE
    internal_reserve: int = 10
    student_outstanding: int = MAX_STUDENT_OUTSTANDING
    bucket_capacity: int = MAX_BUCKET
    refill_seconds: int = 60
    request_budget_seconds: float = 2.0
    interactive_lifetime: timedelta = timedelta(minutes=5)
    internal_lifetime: timedelta = timedelta(minutes=30)

    def __post_init__(self) -> None:
        if (
            not 1 <= self.queue_limit <= MAX_QUEUE
            or not 0 <= self.internal_reserve < self.queue_limit
            or not 1 <= self.student_outstanding <= MAX_STUDENT_OUTSTANDING
            or not 1 <= self.bucket_capacity <= MAX_BUCKET
            or self.refill_seconds < 1
            or not 0 < self.request_budget_seconds <= MAX_ADMISSION_SECONDS
            or not timedelta(seconds=1) < self.interactive_lifetime <= timedelta(minutes=30)
            or not timedelta(seconds=1) < self.internal_lifetime <= timedelta(minutes=30)
        ):
            raise ValueError("Admission limits exceed database safety ceilings")


def retry_delay(job: AiJob, error: AiExecutorError) -> timedelta:
    """Bounded exponential probing plus deterministic per-lease jitter, no extra user token."""
    exponential = timedelta(seconds=min(30, 2 ** max(1, job.attempts)))
    jitter = timedelta(milliseconds=(job.token.int % 1000) if job.token is not None else 0)
    return min(timedelta(minutes=5), max(error.retry_after, exponential + jitter))
