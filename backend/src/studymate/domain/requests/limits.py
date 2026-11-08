from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from studymate.domain.time import require_aware

OUTGOING_PENDING_LIMIT = 5
DAILY_SEND_LIMIT = 10
KUALA_LUMPUR = ZoneInfo("Asia/Kuala_Lumpur")


class RequestQuotaError(Exception):
    pass


def send_day(at: datetime) -> date:
    require_aware(at)
    return at.astimezone(KUALA_LUMPUR).date()


def send_day_bounds(at: datetime) -> tuple[datetime, datetime]:
    start = datetime.combine(send_day(at), time(), KUALA_LUMPUR)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class RequestLimits:
    outgoing_pending: int = OUTGOING_PENDING_LIMIT
    successful_per_day: int = DAILY_SEND_LIMIT

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool) or value < 1
            for value in (self.outgoing_pending, self.successful_per_day)
        ):
            raise ValueError("Request limits must be positive integers")


DEFAULT_LIMITS = RequestLimits()


@dataclass(frozen=True, slots=True)
class SendQuota:
    outgoing_pending: int
    successful_today: int

    def __post_init__(self) -> None:
        if self.outgoing_pending < 0 or self.successful_today < 0:
            raise ValueError("Request quota observations cannot be negative")

    def check(self, limits: RequestLimits = DEFAULT_LIMITS) -> None:
        if (
            self.outgoing_pending >= limits.outgoing_pending
            or self.successful_today >= limits.successful_per_day
        ):
            raise RequestQuotaError
