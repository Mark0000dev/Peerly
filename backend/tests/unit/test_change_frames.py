import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from studymate.application.changes.reads import InvalidChangeCursorError
from studymate.domain.changes import (
    MAX_DELIVERY_SEQUENCE,
    ChangeHint,
    ChangeResource,
    PublishedChange,
)
from studymate.presentation.changes.frames import (
    HEARTBEAT_FRAME,
    change_frame,
    parse_change_cursor,
    reset_frame,
)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "01",
        "-1",
        "+1",
        " 1",
        "1\n",
        "1\r\nid: 5",
        "\uff11",
        "1.0",
        "9" * 20,
        str(MAX_DELIVERY_SEQUENCE + 1),
    ],
)
def test_invalid_cursor_is_not_coerced_or_injected(raw: str) -> None:
    with pytest.raises(InvalidChangeCursorError):
        parse_change_cursor(raw)


@pytest.mark.parametrize("value", [0, 1, (1 << 53) + 1, MAX_DELIVERY_SEQUENCE])
def test_cursor_preserves_bigint_without_javascript_number_roundtrip(value: int) -> None:
    assert parse_change_cursor(str(value)) == value
    assert reset_frame(value) == f"id: {value}\nevent: reset_required\ndata: {{}}\n\n".encode()


@pytest.mark.parametrize("resource", tuple(ChangeResource))
def test_frame_contains_only_allowlisted_invalidation_projection(resource: ChangeResource) -> None:
    hint = ChangeHint(uuid4(), uuid4(), resource, uuid4(), None)
    event = PublishedChange(hint, MAX_DELIVERY_SEQUENCE, datetime.now(UTC))
    frame = change_frame(event).decode()
    lines = frame.splitlines()
    assert lines[:2] == [f"id: {MAX_DELIVERY_SEQUENCE}", "event: resource.changed"]
    assert json.loads(lines[2].removeprefix("data: ")) == {
        "resource_type": resource.value,
        "resource_id": str(hint.resource_id),
        "version": None,
    }
    assert str(hint.recipient_id) not in frame
    assert str(hint.canonical_event_id) not in frame
    assert frame.endswith("\n\n")


def test_heartbeat_does_not_move_cursor_and_absent_header_is_initial_connection() -> None:
    assert HEARTBEAT_FRAME == b": heartbeat\n\n"
    assert parse_change_cursor(None) is None


@pytest.mark.parametrize("sequence", [-1, True, MAX_DELIVERY_SEQUENCE + 1])
def test_reset_rejects_invalid_source_sequence(sequence: int) -> None:
    with pytest.raises(InvalidChangeCursorError):
        reset_frame(sequence)
