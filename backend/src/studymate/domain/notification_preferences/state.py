from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from studymate.domain.time import require_aware


class NotificationMode(StrEnum):
    MESSAGES_AND_REQUESTS = "messages_and_requests"
    ALL_UPDATES = "all_updates"


@dataclass(frozen=True, slots=True)
class NotificationPreference:
    mode: NotificationMode = NotificationMode.MESSAGES_AND_REQUESTS
    version: int = 0
    changed_at: datetime | None = None

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or self.version < 0:
            raise ValueError("Preference version must be nonnegative")
        if self.version == 0:
            if self.mode != NotificationMode.MESSAGES_AND_REQUESTS or self.changed_at is not None:
                raise ValueError("Unchosen preference has the default mode")
        elif self.changed_at is None:
            raise ValueError("Recorded preference requires its actual change time")
        if self.changed_at is not None:
            require_aware(self.changed_at)

    def choose(self, mode: NotificationMode, at: datetime) -> "NotificationPreference":
        require_aware(at)
        if mode == self.mode:
            return self
        return NotificationPreference(mode, self.version + 1, at)
