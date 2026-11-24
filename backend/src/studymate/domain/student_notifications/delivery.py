"""Private-content-free student delivery facts; OS permission is never preference."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.time import require_aware

OPTIONAL_WEEKLY_LIMIT = 2
MAX_ATTEMPTS = 3
QUIET_END_HOUR = 8
QUIET_START_HOUR = 22


class Kind(StrEnum):
    MESSAGE = "message"
    REQUEST = "request"
    ACCEPTED_CONNECTION = "accepted_connection"


class Outcome(StrEnum):
    ACCEPTED = "accepted"
    RETRYABLE = "retryable"  # Provider guarantees no acceptance occurred.
    REJECTED = "rejected"
    UNKNOWN = "unknown"  # Never automatically replay an ambiguous submission.


class State(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SENDING = "sending"
    DELIVERED = "delivered"  # Transport accepted; not device display/read receipt.
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


PREVIEWS = {
    Kind.MESSAGE: "New message about your study request",
    Kind.REQUEST: "New study request for you",
    Kind.ACCEPTED_CONNECTION: "Your study connection was accepted",
}


@dataclass(frozen=True, slots=True)
class Delivery:
    id: UUID
    recipient_id: UUID
    kind: Kind
    expires_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.expires_at)

    @property
    def preview(self) -> str:
        return PREVIEWS[self.kind]


@dataclass(frozen=True, slots=True)
class Claim:
    delivery: Delivery
    token: UUID
    lease_until: datetime

    def __post_init__(self) -> None:
        require_aware(self.lease_until)


@dataclass(frozen=True, slots=True)
class OptionalWindow:
    """Only optional updates: no source is fabricated by this scheduling primitive."""

    mode: NotificationMode
    timezone: str | None
    attempts: tuple[datetime, ...]

    def next_at(self, now: datetime) -> datetime | None:
        require_aware(now)
        if self.mode != NotificationMode.ALL_UPDATES or self.timezone is None:
            return None
        zone = ZoneInfo(self.timezone)  # Invalid IANA input is a programming/validation error.
        for value in self.attempts:
            require_aware(value)
        local = now.astimezone(zone)
        # Approved policy: local calendar days; rolling seven local dates.
        # Conservative across timezone changes: prior attempts still count by actual instant.
        dates = [value.astimezone(zone).date() for value in self.attempts]
        for offset in range(9):
            day = local.date() + timedelta(days=offset)
            week_count = sum(day - timedelta(days=6) <= value <= day for value in dates)
            if day in dates or week_count >= OPTIONAL_WEEKLY_LIMIT:
                continue
            start = datetime.combine(day, time(QUIET_END_HOUR), zone)
            end = datetime.combine(day, time(QUIET_START_HOUR), zone)
            candidate = max(now.astimezone(UTC), start.astimezone(UTC))
            if candidate < end.astimezone(UTC):
                return candidate
        return None


def completion(state: State, outcome: Outcome, attempts: int, expired: bool) -> State:
    if state != State.SENDING:
        raise ValueError("Only a fenced sending attempt can complete")
    if outcome == Outcome.ACCEPTED:
        return State.DELIVERED
    if outcome == Outcome.UNKNOWN:
        return State.UNKNOWN
    if outcome == Outcome.REJECTED:
        return State.REJECTED
    return State.PENDING if attempts < MAX_ATTEMPTS and not expired else State.REJECTED
