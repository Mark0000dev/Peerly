import json
from uuid import uuid4

import pytest

from studymate.application.messaging.history_cursors import (
    InvalidMessageHistoryCursorError,
    MessageHistoryCursor,
    decode_history_cursor,
)
from studymate.infrastructure.messaging.cursors import FernetMessageHistoryCursorCodec


async def test_cursor_is_opaque_and_bound_to_exact_actor_and_conversation() -> None:
    actor, conversation = uuid4(), uuid4()
    codec = FernetMessageHistoryCursorCodec.from_key(b"x" * 32)
    cursor = MessageHistoryCursor(99, 50)
    token = codec.encode(actor, conversation, cursor)
    assert str(actor) not in token
    assert codec.decode(actor, conversation, token) == cursor
    for owner, chat in ((uuid4(), conversation), (actor, uuid4())):
        with pytest.raises(InvalidMessageHistoryCursorError):
            codec.decode(owner, chat, token)
    with pytest.raises(InvalidMessageHistoryCursorError):
        FernetMessageHistoryCursorCodec.from_key(b"y" * 32).decode(actor, conversation, token)


@pytest.mark.parametrize(
    "payload",
    ["", "x" * 1025, "null", "[]", "{}", "[1,2,3,4,5]", '["wrong","actor","chat","2","1"]', "é"],
)
def test_malformed_cursor_never_echoes_input(payload: str) -> None:
    with pytest.raises(InvalidMessageHistoryCursorError) as error:
        decode_history_cursor(uuid4(), uuid4(), payload)
    assert not str(error.value)
    with pytest.raises(InvalidMessageHistoryCursorError):
        FernetMessageHistoryCursorCodec.from_key(b"x" * 32).decode(uuid4(), uuid4(), payload)


@pytest.mark.parametrize(("anchor", "before"), [(0, 1), (1, 0), (1, 2), (True, 1), (1 << 63, 1)])
def test_cursor_requires_bounded_original_committed_sequences(anchor: int, before: int) -> None:
    with pytest.raises(ValueError, match="server sequences"):
        MessageHistoryCursor(anchor, before)


def test_missing_configured_key_is_not_replaced_with_a_default() -> None:
    with pytest.raises(ValueError, match="envelope key"):
        FernetMessageHistoryCursorCodec.from_key(b"")


@pytest.mark.parametrize(("anchor", "before"), [("01", "1"), ("0", "1"), ("2", "3")])
def test_noncanonical_or_invalid_sequence_payloads_are_rejected(anchor: str, before: str) -> None:
    actor, conversation = uuid4(), uuid4()
    payload = json.dumps(
        ("messages-v1", str(actor), str(conversation), anchor, before), separators=(",", ":")
    )
    with pytest.raises(InvalidMessageHistoryCursorError):
        decode_history_cursor(actor, conversation, payload)
