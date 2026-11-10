from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.support.operator_inbox_ports import (
    OperatorSupportHistoryPosition,
    OperatorSupportPosition,
)
from studymate.infrastructure.support.operator_inbox_cursors import (
    FernetOperatorSupportInboxCursorCodec,
)

NOW = datetime(2026, 11, 10, tzinfo=UTC)


def test_search_cursor_is_scoped_to_actor_grant_filters_and_metadata_anchor() -> None:
    codec = FernetOperatorSupportInboxCursorCodec.from_key(b"k" * 32)
    scope = OperatorCursorScope(uuid4(), 1)
    position = OperatorSupportPosition(NOW, NOW - timedelta(seconds=1), uuid4())
    token = codec.encode_inbox(scope, b"h" * 32, position)
    assert codec.decode_inbox(scope, b"h" * 32, token, NOW) == position
    for actor, digest in (
        (replace(scope, account_id=uuid4()), b"h" * 32),
        (replace(scope, access_version=2), b"h" * 32),
        (scope, b"f" * 32),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            codec.decode_inbox(actor, digest, token, NOW)
    with pytest.raises(InvalidOperatorCursorError):
        codec.decode_inbox(scope, b"h" * 32, token, NOW - timedelta(seconds=1))


def test_history_cursor_is_case_grant_and_purpose_bound_and_not_a_read_grant() -> None:
    codec = FernetOperatorSupportInboxCursorCodec.from_key(b"k" * 32)
    scope, case_id = OperatorCursorScope(uuid4(), 1), uuid4()
    position = OperatorSupportHistoryPosition(10, 5)
    token = codec.encode_history(scope, case_id, position)
    assert codec.decode_history(scope, case_id, token) == position
    for actor, case in (
        (replace(scope, account_id=uuid4()), case_id),
        (replace(scope, access_version=2), case_id),
        (scope, uuid4()),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            codec.decode_history(actor, case, token)
    with pytest.raises(InvalidOperatorCursorError):
        codec.decode_inbox(scope, b"h" * 32, token, NOW)
    with pytest.raises(InvalidOperatorCursorError):
        codec.decode_history(scope, case_id, "invalid")
    with pytest.raises(ValueError, match="32-byte"):
        FernetOperatorSupportInboxCursorCodec.from_key(b"bad")
