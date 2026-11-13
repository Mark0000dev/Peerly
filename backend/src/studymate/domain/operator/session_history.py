"""Stored session metadata; dates are facts, never a derived authorization grant."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

SESSION_HISTORY_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class SessionHistoryEntry:
    id: UUID
    account_id: UUID
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
