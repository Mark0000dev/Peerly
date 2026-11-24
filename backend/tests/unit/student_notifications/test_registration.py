from datetime import UTC, datetime
from uuid import uuid4

import pytest

from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.student_notifications.capabilities import Capabilities, Platform, Registration
from studymate.domain.student_notifications.delivery import OptionalWindow


def test_timezone_is_device_supplied_and_unknown_suppresses_only_optional() -> None:
    value = Registration(uuid4(), Platform.ANDROID, True, None, "synthetic-fcm-token")
    assert value.timezone is None
    assert (
        OptionalWindow(NotificationMode.ALL_UPDATES, value.timezone, ()).next_at(
            datetime(2026, 11, 13, tzinfo=UTC)
        )
        is None
    )
    known = Registration(
        uuid4(), Platform.ANDROID, True, "Asia/Kuala_Lumpur", "synthetic-fcm-token"
    )
    assert known.timezone == "Asia/Kuala_Lumpur"
    with pytest.raises(ValueError, match="Invalid IANA"):
        Registration(uuid4(), Platform.ANDROID, True, "Invented/Offset", "token")


def test_disable_erases_transport_material_and_unconfigured_is_truthful() -> None:
    assert not Capabilities().supports(Platform.WEB)
    value = Registration(uuid4(), Platform.WEB, False, None)
    assert value.endpoint is None
    with pytest.raises(ValueError, match="must not retain"):
        Registration(uuid4(), Platform.ANDROID, False, None, "token")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1/private",
        "https://name:secret@push.invalid/a",
        "https://push.invalid:4433/a",
        "https://push.invalid/a#fragment",
    ],
)
def test_web_endpoint_shape_is_closed_before_transport(endpoint: str) -> None:
    with pytest.raises(ValueError, match="HTTPS push"):
        Registration(uuid4(), Platform.WEB, True, "UTC", endpoint, "key", "auth")
