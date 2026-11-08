import json
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.ports import OperatorAccountPosition, OperatorMessagePosition
from studymate.infrastructure.operator.cursors import FernetOperatorCursorCodec
from tests.unit.identity_store import NOW


def test_account_cursor_is_opaque_bound_to_operator_grant_and_filter_fingerprint() -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    codec = FernetOperatorCursorCodec.from_key(b"x" * 32)
    position = OperatorAccountPosition(NOW, NOW - timedelta(seconds=1), uuid4())
    token = codec.encode_accounts(scope, b"y" * 32, position)
    assert str(position.account_id) not in token
    assert codec.decode_accounts(scope, b"y" * 32, token, NOW) == position
    for source, fingerprint in (
        (replace(scope, account_id=uuid4()), b"y" * 32),
        (replace(scope, access_version=2), b"y" * 32),
        (scope, b"z" * 32),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            codec.decode_accounts(source, fingerprint, token, NOW)
    with pytest.raises(InvalidOperatorCursorError):
        codec.decode_accounts(scope, b"y" * 32, token, NOW - timedelta(seconds=1))


def test_message_cursor_requires_same_operator_revision_resource_and_crypto_purpose() -> None:
    scope, conversation = OperatorCursorScope(uuid4(), 1), uuid4()
    codec = FernetOperatorCursorCodec.from_key(b"x" * 32)
    position = OperatorMessagePosition(100, 50)
    token = codec.encode_messages(scope, conversation, position)
    assert codec.decode_messages(scope, conversation, token) == position
    with pytest.raises(InvalidOperatorCursorError):
        codec.decode_messages(scope, uuid4(), token)
    with pytest.raises(InvalidOperatorCursorError):
        codec.decode_messages(replace(scope, access_version=2), conversation, token)
    with pytest.raises(InvalidOperatorCursorError):
        codec.decode_accounts(scope, b"y" * 32, token, NOW)
    with pytest.raises(InvalidOperatorCursorError):
        FernetOperatorCursorCodec.from_key(b"z" * 32).decode_messages(scope, conversation, token)


@pytest.mark.parametrize("token", ["", "x" * 1025, "é", "invalid"])
def test_malformed_cursor_does_not_echo_input_or_supply_authority(token: str) -> None:
    scope, conversation = OperatorCursorScope(uuid4(), 1), uuid4()
    codec = FernetOperatorCursorCodec.from_key(b"x" * 32)
    with pytest.raises(InvalidOperatorCursorError) as error:
        codec.decode_messages(scope, conversation, token)
    assert not str(error.value)


def test_cursor_requires_explicit_existing_key_and_actual_positions() -> None:
    with pytest.raises(ValueError, match="envelope key"):
        FernetOperatorCursorCodec.from_key(b"")
    with pytest.raises(ValueError, match="anchor"):
        OperatorAccountPosition(NOW, NOW + timedelta(seconds=1), uuid4())
    with pytest.raises(ValueError, match="sequences"):
        OperatorMessagePosition(1, 2)
    with pytest.raises(ValueError, match="grant revision"):
        OperatorCursorScope(uuid4(), True)


@pytest.mark.parametrize("payload", ["{}", "[1,2,3,4,5,6]", "invalid-json"])
def test_authenticated_but_malformed_payload_cannot_bypass_typed_cursor_shape(payload: str) -> None:
    codec = FernetOperatorCursorCodec.from_key(b"x" * 32)
    scope, conversation = OperatorCursorScope(uuid4(), 1), uuid4()
    token = codec.messages.encrypt(payload.encode()).decode()
    with pytest.raises(InvalidOperatorCursorError):
        codec.decode_messages(scope, conversation, token)


def test_ciphertext_with_invalid_time_or_sequence_is_rejected_without_raw_values() -> None:
    codec = FernetOperatorCursorCodec.from_key(b"x" * 32)
    scope, conversation = OperatorCursorScope(uuid4(), 1), uuid4()
    account_parts = (
        "operator-accounts-v1",
        str(scope.account_id),
        "1",
        (b"y" * 32).hex(),
        "invalid-date",
        "invalid-date",
        str(uuid4()),
    )
    token = codec.accounts.encrypt(json.dumps(account_parts).encode()).decode()
    with pytest.raises(InvalidOperatorCursorError):
        codec.decode_accounts(scope, b"y" * 32, token, NOW)
    for anchor in ("invalid", "01"):
        parts = ("operator-messages-v1", str(scope.account_id), "1", str(conversation), anchor, "1")
        token = codec.messages.encrypt(json.dumps(parts).encode()).decode()
        with pytest.raises(InvalidOperatorCursorError):
            codec.decode_messages(scope, conversation, token)
    with pytest.raises(ValueError, match="query HMAC"):
        codec.encode_accounts(scope, b"x", OperatorAccountPosition(NOW, NOW, uuid4()))
