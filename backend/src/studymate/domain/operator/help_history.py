"""Raw retained help declarations, including saved clears; no current catalogue policy."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from studymate.domain.time import require_aware

OPERATOR_HELP_HISTORY_PAGE_SIZE = 50
MAX_HELP_HISTORY_VERSION = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class OperatorHelpHistorySelection:
    slot: int
    subject_id: UUID
    subject_label: str = field(repr=False)
    topic_note: str | None = field(repr=False)
    topic_match_key: str | None = field(repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.slot, bool) or self.slot < 0:
            raise ValueError("Retained help selections need an actual nonnegative slot")
        # Exact stored strings/key, never current catalogue/input or matching normalization.


@dataclass(frozen=True, slots=True)
class OperatorHelpHistoryRevision:
    account_id: UUID
    version: int
    selections: tuple[OperatorHelpHistorySelection, ...] = field(repr=False)
    saved_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.saved_at)
        if isinstance(self.version, bool) or not 1 <= self.version <= MAX_HELP_HISTORY_VERSION:
            raise ValueError("Retained help history needs an actual bounded positive version")
        # Empty selections are an actual saved clear, distinct from no revision.
