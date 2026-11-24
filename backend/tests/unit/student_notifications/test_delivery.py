from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.student_notifications.delivery import (
    QUIET_END_HOUR,
    QUIET_START_HOUR,
    Delivery,
    Kind,
    OptionalWindow,
    Outcome,
    State,
    completion,
)


@pytest.mark.parametrize(
    ("hour", "minute", "next_day", "next_hour"),
    [(7, 59, 0, 8), (8, 0, 0, 8), (21, 59, 0, 21), (22, 0, 1, 8), (0, 0, 0, 8)],
)
def test_optional_quiet_boundaries(hour: int, minute: int, next_day: int, next_hour: int) -> None:
    zone = ZoneInfo("Asia/Kuala_Lumpur")
    now = datetime(2026, 11, 13, hour, minute, tzinfo=zone)
    due = OptionalWindow(NotificationMode.ALL_UPDATES, zone.key, ()).next_at(now)
    assert due is not None
    local = due.astimezone(zone)
    assert local.day == now.day + next_day
    assert local.hour == next_hour
    assert local.minute == (minute if hour in (8, 21) else 0)


@pytest.mark.parametrize("zone_name", ["America/New_York", "Europe/Berlin"])
@pytest.mark.parametrize(
    "day", [datetime(2026, 3, 8, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)]
)
def test_optional_local_eight_after_dst_transition(zone_name: str, day: datetime) -> None:
    zone = ZoneInfo(zone_name)
    now = day.replace(hour=6).astimezone(zone)
    due = OptionalWindow(NotificationMode.ALL_UPDATES, zone_name, ()).next_at(now)
    assert due is not None
    assert due >= now
    assert QUIET_END_HOUR <= due.astimezone(zone).hour < QUIET_START_HOUR


def test_opt_out_and_unknown_timezone_fail_closed_immediately() -> None:
    now = datetime(2026, 11, 13, 10, tzinfo=UTC)
    assert OptionalWindow(NotificationMode.MESSAGES_AND_REQUESTS, "UTC", ()).next_at(now) is None
    assert OptionalWindow(NotificationMode.ALL_UPDATES, None, ()).next_at(now) is None


def test_optional_one_local_day_and_two_rolling_seven_local_dates() -> None:
    now = datetime(2026, 11, 13, 10, tzinfo=UTC)
    same_day = OptionalWindow(NotificationMode.ALL_UPDATES, "UTC", (now,)).next_at(now)
    assert same_day == now.replace(day=14, hour=8)
    capped = OptionalWindow(
        NotificationMode.ALL_UPDATES, "UTC", (now - timedelta(days=1), now)
    ).next_at(now)
    assert capped == now.replace(day=19, hour=8)


def test_no_private_preview_content_or_provider_token_slot() -> None:
    expiry = datetime(2026, 11, 13, tzinfo=UTC)
    for kind in Kind:
        message = Delivery(uuid4(), uuid4(), kind, expiry)
        assert "PRIVATE" not in message.preview
        assert set(message.__slots__) == {"id", "recipient_id", "kind", "expires_at"}
    assert (
        Delivery(uuid4(), uuid4(), Kind.MESSAGE, expiry).preview
        == "New message about your study request"
    )


@pytest.mark.parametrize(
    ("outcome", "attempts", "expired", "expected"),
    [
        (Outcome.ACCEPTED, 1, False, State.DELIVERED),
        (Outcome.UNKNOWN, 1, False, State.UNKNOWN),
        (Outcome.REJECTED, 1, False, State.REJECTED),
        (Outcome.RETRYABLE, 1, False, State.PENDING),
        (Outcome.RETRYABLE, 3, False, State.REJECTED),
        (Outcome.RETRYABLE, 1, True, State.REJECTED),
    ],
)
def test_only_definitive_nonacceptance_retries(
    outcome: Outcome, attempts: int, expired: bool, expected: State
) -> None:
    assert completion(State.SENDING, outcome, attempts, expired) == expected


def test_completion_requires_sending_and_aware_times() -> None:
    with pytest.raises(ValueError, match="Only a fenced sending"):
        completion(State.PENDING, Outcome.ACCEPTED, 0, False)
    with pytest.raises(ValueError, match="Domain timestamps"):
        Delivery(uuid4(), uuid4(), Kind.MESSAGE, datetime(2026, 11, 13))
