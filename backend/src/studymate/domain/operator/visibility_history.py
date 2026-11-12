"""Retained visibility sources, never inferred exposure, actor or mutation-event history."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from studymate.domain.time import require_aware

OPERATOR_VISIBILITY_HISTORY_PAGE_SIZE = 50
MAX_VISIBILITY_HISTORY_VERSION = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class OperatorVisibilityHistoryRevision:
    account_id: UUID
    version: int
    completed_at: datetime
    hidden_at: datetime | None
    changed_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.completed_at)
        require_aware(self.changed_at)
        if self.hidden_at is not None:
            require_aware(self.hidden_at)
        if (
            isinstance(self.version, bool)
            or not 1 <= self.version <= MAX_VISIBILITY_HISTORY_VERSION
        ):
            raise ValueError("Visibility history requires an actual bounded positive version")
