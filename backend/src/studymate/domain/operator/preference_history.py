"""Actual retained choices; never synthesize implicit defaults or transport permissions."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.time import require_aware

OPERATOR_PREFERENCE_HISTORY_PAGE_SIZE = 50
MAX_PREFERENCE_HISTORY_VERSION = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class OperatorPreferenceHistoryRevision:
    account_id: UUID
    version: int
    mode: NotificationMode
    changed_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.changed_at)
        if (
            isinstance(self.version, bool)
            or not 1 <= self.version <= MAX_PREFERENCE_HISTORY_VERSION
        ):
            raise ValueError("Preference history requires an actual bounded positive version")
