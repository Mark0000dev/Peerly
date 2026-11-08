import base64
import json
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest

from studymate.application.discovery.cursors import (
    DiscoveryCursor,
    DiscoveryView,
    InvalidDiscoveryCursorError,
    decode_discovery_cursor,
    encode_discovery_cursor,
)
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.discovery_context import DiscoveryContext
from studymate.domain.discovery_order import (
    MAX_FRESHNESS_BUCKET,
    DiscoveryPosition,
    freshness_bucket,
)
from tests.unit.identity_store import NOW


def context() -> DiscoveryContext:
    return DiscoveryContext(UUID(int=1), DiscoveryMode.FIND_HELP, UUID(int=2), 1, None)


def cursor() -> DiscoveryCursor:
    return DiscoveryCursor(NOW, DiscoveryPosition(True, 0, UUID(int=3)))


def test_discovery_cursor_roundtrip_is_canonical_and_frozen_to_query_time() -> None:
    scope = context()
    value = cursor()
    encoded = encode_discovery_cursor(scope, DiscoveryView.CANDIDATES, value)
    assert decode_discovery_cursor(scope, DiscoveryView.CANDIDATES, encoded, NOW) == value
    assert (
        decode_discovery_cursor(scope, DiscoveryView.CANDIDATES, encoded, NOW + timedelta(days=1))
        == value
    )


@pytest.mark.parametrize("change", ["actor", "goal", "revision", "mode", "help", "view"])
def test_cursor_cannot_cross_owner_context_mode_or_view(change: str) -> None:
    scope = context()
    encoded = encode_discovery_cursor(scope, DiscoveryView.CANDIDATES, cursor())
    view = DiscoveryView.CANDIDATES
    if change == "actor":
        scope = replace(scope, account_id=UUID(int=10))
    elif change == "goal":
        scope = replace(scope, goal_id=UUID(int=10))
    elif change == "revision":
        scope = replace(scope, goal_version=2)
    elif change == "mode":
        scope = replace(scope, mode=DiscoveryMode.STUDY_TOGETHER)
    elif change == "help":
        scope = DiscoveryContext(scope.account_id, DiscoveryMode.OFFER_HELP, None, None, 1)
    else:
        view = DiscoveryView.PASSED
    with pytest.raises(InvalidDiscoveryCursorError):
        decode_discovery_cursor(scope, view, encoded, NOW)


@pytest.mark.parametrize("encoded", ["", "=", "a" * 1025, "%%%", "e30", "bnVsbA", "_w"])
def test_malformed_or_oversized_cursor_is_rejected(encoded: str) -> None:
    with pytest.raises(InvalidDiscoveryCursorError):
        decode_discovery_cursor(context(), DiscoveryView.CANDIDATES, encoded, NOW)


@pytest.mark.parametrize("value", [True, "-1", "31", "01", "not-a-number", None])
def test_cursor_sort_values_are_strict_and_canonical(value: str | bool | None) -> None:
    encoded = encode_discovery_cursor(context(), DiscoveryView.CANDIDATES, cursor())
    payload: list[object] = json.loads(
        base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    )
    payload[-2] = value
    changed = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    with pytest.raises(InvalidDiscoveryCursorError):
        decode_discovery_cursor(context(), DiscoveryView.CANDIDATES, changed, NOW)


def test_future_query_time_and_noncanonical_padding_are_rejected() -> None:
    encoded = encode_discovery_cursor(context(), DiscoveryView.CANDIDATES, cursor())
    with pytest.raises(InvalidDiscoveryCursorError):
        decode_discovery_cursor(
            context(), DiscoveryView.CANDIDATES, encoded, NOW - timedelta(seconds=1)
        )
    with pytest.raises(InvalidDiscoveryCursorError):
        decode_discovery_cursor(context(), DiscoveryView.CANDIDATES, encoded + "=", NOW)


def test_topic_then_bounded_activity_then_stable_id_order_never_uses_reputation() -> None:
    recent = DiscoveryPosition(False, 0, UUID(int=1))
    same_topic = DiscoveryPosition(True, MAX_FRESHNESS_BUCKET, UUID(int=4))
    newcomer = DiscoveryPosition(False, 0, UUID(int=2))
    older = DiscoveryPosition(False, 1, UUID(int=3))
    assert sorted((older, newcomer, same_topic, recent), key=lambda item: item.sort_key) == [
        same_topic,
        recent,
        newcomer,
        older,
    ]
    assert freshness_bucket(NOW + timedelta(hours=1), NOW) == 0
    assert freshness_bucket(NOW - timedelta(days=200), NOW) == MAX_FRESHNESS_BUCKET
    assert freshness_bucket(NOW - timedelta(hours=23), NOW) == 0


@pytest.mark.parametrize("bucket", [True, -1, MAX_FRESHNESS_BUCKET + 1])
def test_invalid_freshness_bucket_is_rejected(bucket: int) -> None:
    with pytest.raises(ValueError, match="bounded internal bucket"):
        DiscoveryPosition(False, bucket, UUID(int=1))
