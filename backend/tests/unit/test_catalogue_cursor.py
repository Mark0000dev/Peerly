import base64
import json
from uuid import uuid4

import pytest

from studymate.application.catalogue import CatalogueCursor
from studymate.presentation.catalogue import (
    InvalidCatalogueCursorError,
    decode_cursor,
    encode_cursor,
)


def test_catalogue_cursor_is_opaque_bounded_and_preserves_unicode_position() -> None:
    original = CatalogueCursor("synthetic 中文", uuid4(), "中文")
    encoded = encode_cursor(original)
    assert encoded is not None
    assert "中文" not in encoded
    assert decode_cursor(encoded) == original
    assert encode_cursor(None) is None
    assert decode_cursor(None) is None


@pytest.mark.parametrize("value", ["", "=", "x", "x" * 2049])
def test_malformed_catalogue_cursor_is_rejected_before_querying(value: str) -> None:
    with pytest.raises(InvalidCatalogueCursorError):
        decode_cursor(value)


@pytest.mark.parametrize("name", ["private\x00text", "\ud800", "", "x" * 241])
def test_cursor_json_cannot_smuggle_database_invalid_text(name: str) -> None:
    body = json.dumps(
        {"normalized_name": name, "subject_id": str(uuid4()), "query_key": ""}
    ).encode()
    token = base64.urlsafe_b64encode(body).decode().rstrip("=")
    with pytest.raises(InvalidCatalogueCursorError):
        decode_cursor(token)
