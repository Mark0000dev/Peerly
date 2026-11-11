from dataclasses import replace
from uuid import UUID

import pytest

from studymate.application.discovery.cursors import (
    DiscoveryView,
    InvalidDiscoveryCursorError,
    encode_discovery_cursor,
)
from studymate.infrastructure.security.discovery_cursor import FernetDiscoveryCursorCodec
from tests.unit.identity_store import NOW
from tests.unit.test_discovery_cursors import context, cursor


def test_encrypted_cursor_roundtrip_survives_new_adapter_with_same_configured_key() -> None:
    first = FernetDiscoveryCursorCodec.from_key(bytes(range(32)))
    token = first.encode(context(), DiscoveryView.CANDIDATES, cursor())
    second = FernetDiscoveryCursorCodec.from_key(bytes(range(32)))
    assert second.decode(context(), DiscoveryView.CANDIDATES, token, NOW) == cursor()
    assert token != encode_discovery_cursor(context(), DiscoveryView.CANDIDATES, cursor())
    assert "discovery-v1" not in token


def test_plain_or_tampered_or_wrong_key_cursor_has_no_fallback() -> None:
    codec = FernetDiscoveryCursorCodec.from_key(bytes(range(32)))
    token = codec.encode(context(), DiscoveryView.CANDIDATES, cursor())
    offset = len(token) // 2
    changed = token[:offset] + ("A" if token[offset] != "A" else "B") + token[offset + 1 :]
    for value in (
        changed,
        encode_discovery_cursor(context(), DiscoveryView.CANDIDATES, cursor()),
        "x" * 1025,
        "☃",
    ):
        with pytest.raises(InvalidDiscoveryCursorError):
            codec.decode(context(), DiscoveryView.CANDIDATES, value, NOW)
    other = FernetDiscoveryCursorCodec.from_key(bytes(reversed(range(32))))
    with pytest.raises(InvalidDiscoveryCursorError):
        other.decode(context(), DiscoveryView.CANDIDATES, token, NOW)


def test_valid_encryption_does_not_override_context_owner_and_view_binding() -> None:
    codec = FernetDiscoveryCursorCodec.from_key(bytes(range(32)))
    token = codec.encode(context(), DiscoveryView.CANDIDATES, cursor())
    with pytest.raises(InvalidDiscoveryCursorError):
        codec.decode(
            replace(context(), account_id=UUID(int=99)), DiscoveryView.CANDIDATES, token, NOW
        )
    with pytest.raises(InvalidDiscoveryCursorError):
        codec.decode(context(), DiscoveryView.PASSED, token, NOW)


def test_envelope_key_length_is_explicit() -> None:
    with pytest.raises(ValueError, match="32-byte envelope key"):
        FernetDiscoveryCursorCodec.from_key(b"short")
