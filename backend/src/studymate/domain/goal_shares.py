"""Explicit immutable own-goal shares, separate from human messages and request context."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from studymate.domain.relationships import AccountPair
from studymate.domain.study_context import CustomSubjectRef, StudyGoal
from studymate.domain.text import plain_text
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class GoalShare:
    id: UUID
    conversation_id: UUID
    pair: AccountPair
    owner_id: UUID
    context_version: int
    goal: StudyGoal = field(repr=False)
    subject_label: str = field(repr=False)
    shared_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.shared_at)
        if (
            self.owner_id not in (self.pair.low, self.pair.high)
            or self.goal.account_id != self.owner_id
        ):
            raise ValueError("Shared goal must belong to its actual conversation participant")
        if isinstance(self.context_version, bool) or self.context_version < 1:
            raise ValueError("Actual shared goal context version must be positive")
        if not self.goal.active or self.shared_at < self.goal.updated_at:
            raise ValueError("Shared snapshot must be active at the actual share time")
        plain_text(self.subject_label, minimum=1, maximum=80)
        if (
            isinstance(self.goal.content.subject, CustomSubjectRef)
            and self.goal.content.subject.label != self.subject_label
        ):
            raise ValueError("Custom goal label must match its immutable source")


@dataclass(frozen=True, slots=True)
class GoalShareState:
    context_version: int
    latest: GoalShare | None = field(repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.context_version, bool) or self.context_version < 0:
            raise ValueError("Goal context version must be nonnegative")
        if (self.latest is None) != (self.context_version == 0):
            raise ValueError("Context zero is the actual request baseline, never a share row")
        if self.latest is not None and self.latest.context_version != self.context_version:
            raise ValueError("Latest shared context must match its actual source version")
