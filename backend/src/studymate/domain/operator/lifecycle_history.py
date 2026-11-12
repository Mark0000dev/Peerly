"""Exact retained lifecycle provenance for privileged inspection."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from studymate.domain.lifecycle.states import LifecycleOperation
from studymate.domain.time import require_aware

OPERATOR_LIFECYCLE_HISTORY_PAGE_SIZE = 50
MAX_LIFECYCLE_HISTORY_VERSION = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class OperatorLifecycleHistoryRevision:
    id: UUID
    account_id: UUID
    version: int
    previous_version: int | None
    operation: LifecycleOperation
    before_banned_at: datetime | None
    before_deleted_at: datetime | None
    after_banned_at: datetime | None
    after_deleted_at: datetime | None
    changed_at: datetime
    actor_id: UUID
    actor_session_id: UUID
    operator_access_version: int | None
    operator_access_active: bool | None
    reason: str | None = field(repr=False)
    workflow_id: UUID | None
    http_request_id: UUID | None
    action_id: UUID | None
    trace_id: str | None
    span_id: str | None

    def __post_init__(self) -> None:
        require_aware(self.changed_at)
        if isinstance(self.version, bool) or not 1 <= self.version <= MAX_LIFECYCLE_HISTORY_VERSION:
            raise ValueError("Lifecycle history requires an actual bounded positive version")
