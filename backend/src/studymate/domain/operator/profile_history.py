"""Exact retained profile revisions; no current profile/photo or disclosure authority."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from studymate.domain.profiles import OnboardingTask
from studymate.domain.time import require_aware

OPERATOR_PROFILE_HISTORY_PAGE_SIZE = 50
MAX_PROFILE_HISTORY_VERSION = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class OperatorProfileHistoryRevision:
    account_id: UUID
    version: int
    display_name: str | None = field(repr=False)
    about: str | None = field(repr=False)
    programme: str | None = field(repr=False)
    year_label: str | None = field(repr=False)
    languages: tuple[str, ...] = field(repr=False)
    task: OnboardingTask
    saved_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.saved_at)
        if isinstance(self.version, bool) or not 1 <= self.version <= MAX_PROFILE_HISTORY_VERSION:
            raise ValueError("Retained profile history needs an actual bounded positive version")
        # Raw retained fields: never reapply current submission length/language/catalogue policy.
