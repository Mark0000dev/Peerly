"""Raw retained goal roots/revisions, never current goal validation or matching authority."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from studymate.domain.time import require_aware

OPERATOR_GOAL_PAGE_SIZE = 50
MAX_OPERATOR_GOAL_VERSION = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class OperatorGoalRoot:
    id: UUID
    account_id: UUID
    current_version: int
    created_at: datetime
    completed_at: datetime | None

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        if self.completed_at is not None:
            require_aware(self.completed_at)
        if (
            isinstance(self.current_version, bool)
            or not 1 <= self.current_version <= MAX_OPERATOR_GOAL_VERSION
        ):
            raise ValueError("Retained goal root needs an actual bounded source version")


@dataclass(frozen=True, slots=True)
class OperatorGoalRevision:
    goal_id: UUID
    account_id: UUID
    version: int
    subject_id: UUID | None
    subject_label: str = field(repr=False)
    topic: str | None = field(repr=False)
    topic_match_key: str | None = field(repr=False)
    context: str | None = field(repr=False)
    shared_learning: bool
    saved_at: datetime
    completed_at: datetime | None

    def __post_init__(self) -> None:
        require_aware(self.saved_at)
        if self.completed_at is not None:
            require_aware(self.completed_at)
        if isinstance(self.version, bool) or not 1 <= self.version <= MAX_OPERATOR_GOAL_VERSION:
            raise ValueError("Retained goal revision needs an actual bounded source version")
        # No GoalContent/StudyGoal/current catalogue or cross-timestamp/content policy.
