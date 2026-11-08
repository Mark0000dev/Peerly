import json
from uuid import uuid4

import pytest

from studymate.application.messaging.goal_shares import (
    GoalShareCursor,
    InvalidGoalShareCursorError,
    decode_goal_share_cursor,
)
from studymate.infrastructure.messaging.goal_share_cursors import FernetGoalShareCursorCodec


def test_goal_context_cursor_is_not_a_message_cursor_or_another_actors_grant() -> None:
    actor, conversation = uuid4(), uuid4()
    codec = FernetGoalShareCursorCodec.from_key(b"x" * 32)
    cursor = GoalShareCursor(51, 2)
    token = codec.encode(actor, conversation, cursor)
    assert str(conversation) not in token
    assert codec.decode(actor, conversation, token) == cursor
    for owner, convo in ((uuid4(), conversation), (actor, uuid4())):
        with pytest.raises(InvalidGoalShareCursorError):
            codec.decode(owner, convo, token)
    with pytest.raises(InvalidGoalShareCursorError):
        FernetGoalShareCursorCodec.from_key(b"y" * 32).decode(actor, conversation, token)


@pytest.mark.parametrize("payload", ["", "x" * 1025, "{}", "null", "[]", "[1,2,3,4,5]", "é"])
def test_malformed_share_cursor_is_bounded_and_does_not_echo_input(payload: str) -> None:
    actor, conversation = uuid4(), uuid4()
    with pytest.raises(InvalidGoalShareCursorError) as error:
        decode_goal_share_cursor(actor, conversation, payload)
    assert not str(error.value)
    with pytest.raises(InvalidGoalShareCursorError):
        FernetGoalShareCursorCodec.from_key(b"x" * 32).decode(actor, conversation, payload)


@pytest.mark.parametrize(("anchor", "before"), [("01", "1"), ("0", "1"), ("1", "2")])
def test_share_cursor_requires_canonical_bounded_source_versions(anchor: str, before: str) -> None:
    actor, conversation = uuid4(), uuid4()
    payload = json.dumps(
        ("goal-shares-v1", str(actor), str(conversation), anchor, before), separators=(",", ":")
    )
    with pytest.raises(InvalidGoalShareCursorError):
        decode_goal_share_cursor(actor, conversation, payload)


def test_wrong_namespace_and_missing_key_do_not_silently_fallback() -> None:
    with pytest.raises(InvalidGoalShareCursorError):
        decode_goal_share_cursor(uuid4(), uuid4(), '["messages-v1","actor","conversation","2","1"]')
    with pytest.raises(ValueError, match="envelope key"):
        FernetGoalShareCursorCodec.from_key(b"")
    with pytest.raises(ValueError, match="context versions"):
        GoalShareCursor(True, 1)
