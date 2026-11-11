from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.application.requests.cursors import (
    InvalidRequestCursorError,
    RequestCursor,
    decode_request_cursor,
    encode_request_cursor,
)
from studymate.domain.requests.projections import RequestBox, RequestListView
from studymate.infrastructure.requests.cursors import FernetRequestCursorCodec
from tests.unit.identity_store import NOW
from tests.unit.requests.store import SENDER


def test_encrypted_cursor_is_bound_to_actor_box_view_and_anchor() -> None:
    codec = FernetRequestCursorCodec.from_key(b"x" * 32)
    cursor = RequestCursor(NOW, NOW - timedelta(seconds=1), uuid4())
    token = codec.encode(SENDER, RequestBox.RECEIVED, RequestListView.ACTIVE, cursor)
    assert str(cursor.request_id) not in token
    assert codec.decode(SENDER, RequestBox.RECEIVED, RequestListView.ACTIVE, token, NOW) == cursor
    for actor, box, view in (
        (uuid4(), RequestBox.RECEIVED, RequestListView.ACTIVE),
        (SENDER, RequestBox.SENT, RequestListView.ACTIVE),
        (SENDER, RequestBox.RECEIVED, RequestListView.HISTORY),
    ):
        with pytest.raises(InvalidRequestCursorError):
            codec.decode(actor, box, view, token, NOW)
    with pytest.raises(InvalidRequestCursorError):
        codec.decode(
            SENDER, RequestBox.RECEIVED, RequestListView.ACTIVE, token, NOW - timedelta(seconds=1)
        )
    other = FernetRequestCursorCodec.from_key(b"y" * 32)
    with pytest.raises(InvalidRequestCursorError):
        other.decode(SENDER, RequestBox.RECEIVED, RequestListView.ACTIVE, token, NOW)


@pytest.mark.parametrize("token", ["", "!", "a" * 1025, "é", "e30", "W10", "bnVsbA", "WyJ4Il0"])
def test_malformed_cursors_fail_without_echoing_private_data(token: str) -> None:
    with pytest.raises(InvalidRequestCursorError) as error:
        decode_request_cursor(SENDER, RequestBox.RECEIVED, RequestListView.ACTIVE, token, NOW)
    assert not str(error.value)
    codec = FernetRequestCursorCodec.from_key(b"x" * 32)
    with pytest.raises(InvalidRequestCursorError):
        codec.decode(SENDER, RequestBox.RECEIVED, RequestListView.ACTIVE, token, NOW)


def test_cursor_rejects_future_send_and_missing_key() -> None:
    with pytest.raises(ValueError, match="query anchor"):
        RequestCursor(NOW, NOW + timedelta(seconds=1), uuid4())
    with pytest.raises(ValueError, match="envelope key"):
        FernetRequestCursorCodec.from_key(b"")
    cursor = RequestCursor(NOW, NOW, uuid4())
    encoded = encode_request_cursor(SENDER, RequestBox.SENT, RequestListView.HISTORY, cursor)
    assert (
        decode_request_cursor(SENDER, RequestBox.SENT, RequestListView.HISTORY, encoded, NOW)
        == cursor
    )
