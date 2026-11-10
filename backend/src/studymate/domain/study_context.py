"""Versioned knowledge-area declarations; no enrolment or verified-competence claims."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from studymate.domain.text import optional_text, plain_text
from studymate.domain.time import require_aware

MAX_TOPIC_LENGTH = 80
MAX_CONTEXT_LENGTH = 240
MAX_HELP_SUBJECTS = 5


class GoalClosedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CanonicalSubjectRef:
    id: UUID


@dataclass(frozen=True, slots=True)
class CustomSubjectRef:
    label: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "label",
            plain_text(self.label, minimum=1, maximum=MAX_TOPIC_LENGTH, collapse_spaces=True),
        )


type SubjectRef = CanonicalSubjectRef | CustomSubjectRef


@dataclass(frozen=True, slots=True)
class GoalContent:
    subject: SubjectRef
    topic: str | None = field(default=None, repr=False)
    context: str | None = field(default=None, repr=False)
    shared_learning: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "topic", optional_text(self.topic, maximum=MAX_TOPIC_LENGTH))
        object.__setattr__(
            self, "context", optional_text(self.context, maximum=MAX_CONTEXT_LENGTH, multiline=True)
        )

    @property
    def canonical_subject_id(self) -> UUID | None:
        return self.subject.id if isinstance(self.subject, CanonicalSubjectRef) else None


@dataclass(frozen=True, slots=True)
class StudyGoal:
    id: UUID
    account_id: UUID
    version: int
    content: GoalContent = field(repr=False)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        require_aware(self.updated_at)
        if isinstance(self.version, bool) or self.version < 1 or self.updated_at < self.created_at:
            raise ValueError("Goal version and timestamps must be valid")
        if self.completed_at is not None:
            require_aware(self.completed_at)
            if self.completed_at != self.updated_at:
                raise ValueError("Completed goal timestamp must be its final revision time")

    @property
    def active(self) -> bool:
        return self.completed_at is None

    def revise(self, content: GoalContent, at: datetime) -> "StudyGoal":
        self._check_time(at)
        if not self.active:
            raise GoalClosedError("Completed goal cannot be edited")
        if content == self.content:
            return self
        return replace(self, content=content, version=self.version + 1, updated_at=at)

    def complete(self, at: datetime) -> "StudyGoal":
        self._check_time(at)
        if not self.active:
            return self
        return replace(self, version=self.version + 1, updated_at=at, completed_at=at)

    def _check_time(self, at: datetime) -> None:
        require_aware(at)
        if at < self.updated_at:
            raise ValueError("Goal update cannot precede its latest revision")


@dataclass(frozen=True, slots=True)
class HelpSubject:
    subject_id: UUID
    topic_note: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "topic_note", optional_text(self.topic_note, maximum=MAX_TOPIC_LENGTH)
        )


@dataclass(frozen=True, slots=True)
class HelpSubjects:
    values: tuple[HelpSubject, ...] = ()

    def __post_init__(self) -> None:
        if len(self.values) > MAX_HELP_SUBJECTS or len(
            {value.subject_id for value in self.values}
        ) != len(self.values):
            raise ValueError("Help subjects must be distinct and within the allowed maximum")


@dataclass(frozen=True, slots=True)
class HelpRevision:
    account_id: UUID
    version: int
    subjects: HelpSubjects = field(repr=False)
    saved_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.saved_at)
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Help revision must be positive")
