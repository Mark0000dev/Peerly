from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from studymate.domain.time import require_aware

MAX_FRESHNESS_BUCKET = 30


def freshness_bucket(activity_at: datetime, as_of: datetime) -> int:
    """Internal daily buckets are not presence or promised partner availability."""
    require_aware(activity_at)
    require_aware(as_of)
    return max(0, min(MAX_FRESHNESS_BUCKET, (as_of - activity_at) // timedelta(days=1)))


@dataclass(frozen=True, slots=True)
class DiscoveryPosition:
    same_topic: bool
    freshness: int
    person_id: UUID

    def __post_init__(self) -> None:
        if isinstance(self.freshness, bool) or not 0 <= self.freshness <= MAX_FRESHNESS_BUCKET:
            raise ValueError("Discovery freshness must be a bounded internal bucket")

    @property
    def sort_key(self) -> tuple[bool, int, int]:
        return not self.same_topic, self.freshness, self.person_id.int
