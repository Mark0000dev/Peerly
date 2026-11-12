"""Exact retained operator grants/revocations; historical active is not current authority."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from studymate.domain.time import require_aware

OPERATOR_ACCESS_HISTORY_PAGE_SIZE = 50
MAX_ACCESS_HISTORY_VERSION = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class OperatorAccessHistoryRevision:
    account_id: UUID
    version: int
    active: bool
    changed_at: datetime
    changed_by_id: UUID | None
    http_request_id: UUID | None
    action_id: UUID | None
    trace_id: str | None
    span_id: str | None

    def __post_init__(self) -> None:
        require_aware(self.changed_at)
        if isinstance(self.version, bool) or not 1 <= self.version <= MAX_ACCESS_HISTORY_VERSION:
            raise ValueError("Operator-access history requires an actual bounded positive version")
