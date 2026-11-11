import json
from datetime import timedelta
from uuid import UUID

import pytest

from studymate.application.messaging.conversation_list import (
    ConversationListCursor,
    InvalidConversationCursorError,
)
from studymate.infrastructure.persistence.conversation_cursors import (
    CURSOR_LIFETIME,
    FernetConversationListCursorCodec,
)
from studymate.infrastructure.requests.cursors import FernetRequestCursorCodec
from tests.unit.identity_store import NOW

ACTOR = UUID(int=2)
CURSOR = ConversationListCursor(NOW, NOW - timedelta(seconds=1), UUID(int=90))


def test_actual_encrypted_cursor_roundtrip_hides_source_and_binds_actor_and_key() -> None:
    codec = FernetConversationListCursorCodec.from_key(b"a" * 32)
    token = codec.encode(ACTOR, CURSOR)
    assert codec.decode(ACTOR, token, NOW) == CURSOR
    assert str(ACTOR) not in token
    assert "conversations-v1" not in token
    for bad_codec, actor in (
        (codec, UUID(int=3)),
        (FernetConversationListCursorCodec.from_key(b"b" * 32), ACTOR),
        (
            FernetConversationListCursorCodec(FernetRequestCursorCodec.from_key(b"a" * 32).cipher),
            ACTOR,
        ),
    ):
        with pytest.raises(InvalidConversationCursorError):
            bad_codec.decode(actor, token, NOW)


@pytest.mark.parametrize("token", ["", "malformed", "x" * 1025, "\ud800"])
def test_invalid_envelopes_are_safe_cursor_errors(token: str) -> None:
    with pytest.raises(InvalidConversationCursorError):
        FernetConversationListCursorCodec.from_key(b"a" * 32).decode(ACTOR, token, NOW)


@pytest.mark.parametrize("offset", [-1, 3601])
def test_future_or_expired_query_anchor_is_rejected(offset: int) -> None:
    codec = FernetConversationListCursorCodec.from_key(b"a" * 32)
    with pytest.raises(InvalidConversationCursorError):
        codec.decode(ACTOR, codec.encode(ACTOR, CURSOR), NOW + timedelta(seconds=offset))
    assert codec.decode(ACTOR, codec.encode(ACTOR, CURSOR), NOW + CURSOR_LIFETIME) == CURSOR


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "null",
        "{}",
        "[]",
        '["a",1,2,3,4]',
        json.dumps(["other", str(ACTOR), NOW.isoformat(), NOW.isoformat(), str(UUID(int=90))]),
        json.dumps(["conversations-v1", str(ACTOR), "broken", NOW.isoformat(), str(UUID(int=90))]),
        json.dumps(
            [
                "conversations-v1",
                str(ACTOR),
                NOW.replace(tzinfo=None).isoformat(),
                NOW.isoformat(),
                str(UUID(int=90)),
            ]
        ),
    ],
)
def test_authenticated_but_malformed_payload_does_not_escape_as_private_error(payload: str) -> None:
    codec = FernetConversationListCursorCodec.from_key(b"a" * 32)
    token = codec.cipher.encrypt(payload.encode()).decode()
    with pytest.raises(InvalidConversationCursorError):
        codec.decode(ACTOR, token, NOW)


def test_invalid_encryption_key_is_configuration_error() -> None:
    with pytest.raises(ValueError, match="32-byte"):
        FernetConversationListCursorCodec.from_key(b"short")
