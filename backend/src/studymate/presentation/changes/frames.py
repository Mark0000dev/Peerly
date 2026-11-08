"""Content-free SSE framing; delivery IDs are opaque decimal strings to browsers."""

import json

from studymate.application.changes.reads import InvalidChangeCursorError
from studymate.domain.changes import MAX_DELIVERY_SEQUENCE, PublishedChange


def parse_change_cursor(value: str | None) -> int | None:
    if value is None:
        return None
    if (
        not value
        or len(value) > len(str(MAX_DELIVERY_SEQUENCE))
        or not value.isascii()
        or not value.isdecimal()
        or (len(value) > 1 and value.startswith("0"))
    ):
        raise InvalidChangeCursorError
    result = int(value)
    if result > MAX_DELIVERY_SEQUENCE:
        raise InvalidChangeCursorError
    return result


def change_frame(change: PublishedChange) -> bytes:
    hint = change.hint
    data = json.dumps(
        {
            "resource_type": hint.resource_type.value,
            "resource_id": str(hint.resource_id),
            "version": hint.version,
        },
        separators=(",", ":"),
    )
    return f"id: {change.sequence}\nevent: resource.changed\ndata: {data}\n\n".encode()


def reset_frame(sequence: int) -> bytes:
    if isinstance(sequence, bool) or not 0 <= sequence <= MAX_DELIVERY_SEQUENCE:
        raise InvalidChangeCursorError
    return f"id: {sequence}\nevent: reset_required\ndata: {{}}\n\n".encode("ascii")


HEARTBEAT_FRAME = b": heartbeat\n\n"
