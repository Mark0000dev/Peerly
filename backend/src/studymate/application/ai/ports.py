from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentityReader
from studymate.domain.ai.jobs import AiJob, Failure, Versions
from studymate.domain.ai.tasks import (
    MAX_CANDIDATES,
    AiKind,
    AiResult,
    AiTask,
    GoalTextTarget,
    Source,
)
from studymate.domain.study_context import MAX_TOPIC_LENGTH
from studymate.domain.text import plain_text


class AiUnavailableError(Exception):
    pass


class AiQuotaError(Exception):
    pass


class AiSourceUnavailableError(Exception):
    pass


class AiJobNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class DraftSourceIntent:
    id: UUID
    version: int
    kind: Literal["draft"] = "draft"

    def __post_init__(self) -> None:
        Source(self.id, self.version)


@dataclass(frozen=True, slots=True)
class StudentSubmission:
    kind: AiKind
    source: Source | DraftSourceIntent
    text: str | None = field(default=None, repr=False)
    candidate_ids: tuple[UUID, ...] = ()
    target: GoalTextTarget = GoalTextTarget.CONTEXT
    label: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.source, DraftSourceIntent) and self.kind == AiKind.ASSESS_PHOTO:
            raise ValueError("Photo advice requires an owned resource, not a draft")
        if self.kind != AiKind.CLARIFY_GOAL and self.target != GoalTextTarget.CONTEXT:
            raise ValueError("This task does not accept a clarification target")
        if self.kind == AiKind.TRIAGE_REPORT:
            raise ValueError("Internal triage is not a student operation")
        if self.kind == AiKind.CLARIFY_GOAL:
            if self.text is None or not self.text.strip() or len(self.text) > self.target.maximum:
                raise ValueError("Explicit bounded goal text required")
            plain_text(
                self.text,
                minimum=1,
                maximum=self.target.maximum,
                multiline=self.target == GoalTextTarget.CONTEXT,
            )
        elif self.text is not None:
            raise ValueError("This task does not accept arbitrary text")
        if isinstance(self.source, DraftSourceIntent) and self.kind == AiKind.SUGGEST_SUBJECT:
            if self.label is None or len(self.label) > MAX_TOPIC_LENGTH:
                raise ValueError("Explicit bounded draft subject label required")
            plain_text(self.label, minimum=1, maximum=MAX_TOPIC_LENGTH)
        elif self.label is not None:
            raise ValueError("This task does not accept a draft label")
        if self.kind == AiKind.SUGGEST_SUBJECT:
            if not 1 <= len(self.candidate_ids) <= MAX_CANDIDATES or len(
                set(self.candidate_ids)
            ) != len(self.candidate_ids):
                raise ValueError("Bounded distinct catalogue candidates required")
        elif self.candidate_ids:
            raise ValueError("This task does not accept catalogue candidates")


@dataclass(frozen=True, slots=True)
class Admission:
    actor_id: UUID
    task: AiTask = field(repr=False)
    key: IntentKey
    digest: bytes = field(repr=False)
    versions: Versions


class AiTransaction(IdentityReader, Protocol):
    async def replay(
        self, actor_id: UUID, kind: AiKind, key: IntentKey, digest: bytes
    ) -> AiJob | None: ...

    async def prepare(self, actor_id: UUID, submission: StudentSubmission) -> AiTask: ...

    async def admit(self, intent: "Admission", at: datetime) -> AiJob: ...

    async def owned(self, actor_id: UUID, job_id: UUID, *, cancel: bool = False) -> AiJob: ...


class AiUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[AiTransaction]: ...


class AiExecutorError(Exception):
    def __init__(self, failure: Failure, retry_after: timedelta = timedelta(seconds=2)) -> None:
        super().__init__(failure.value)
        self.failure = failure
        self.retry_after = retry_after


class AiExecutor(Protocol):
    async def execute(self, task: AiTask, budget_seconds: float) -> AiResult: ...
