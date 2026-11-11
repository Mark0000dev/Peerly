import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from studymate.domain.requests.projections import RequestBox, RequestListView
from studymate.domain.time import require_aware

CURSOR_PARTS = 7
CURSOR_LIMIT = 1024


class InvalidRequestCursorError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RequestCursor:
    as_of: datetime
    sent_at: datetime
    request_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.as_of)
        require_aware(self.sent_at)
        if self.sent_at > self.as_of:
            raise ValueError("Request cursor cannot include a send after its query anchor")


class RequestCursorCodec(Protocol):
    def encode(
        self, actor_id: UUID, box: RequestBox, view: RequestListView, cursor: RequestCursor
    ) -> str: ...

    def decode(
        self, actor_id: UUID, box: RequestBox, view: RequestListView, token: str, now: datetime
    ) -> RequestCursor: ...


def encode_request_cursor(
    actor_id: UUID, box: RequestBox, view: RequestListView, cursor: RequestCursor
) -> str:
    payload = json.dumps(
        (
            "requests-v1",
            str(actor_id),
            box.value,
            view.value,
            cursor.as_of.astimezone(UTC).isoformat(),
            cursor.sent_at.astimezone(UTC).isoformat(),
            str(cursor.request_id),
        ),
        separators=(",", ":"),
    ).encode("ascii")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_request_cursor(
    actor_id: UUID, box: RequestBox, view: RequestListView, encoded: str, now: datetime
) -> RequestCursor:
    require_aware(now)
    if re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", encoded) is None:
        raise InvalidRequestCursorError
    try:
        data: object = json.loads(
            base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        )
        if (
            not isinstance(data, list)
            or len(data) != CURSOR_PARTS
            or not all(isinstance(item, str) for item in data)
        ):
            raise InvalidRequestCursorError
        strings = tuple(item for item in data if isinstance(item, str))
        version, actor, encoded_box, encoded_view, anchor, sent, request_id = strings
        if (version, actor, encoded_box, encoded_view) != (
            "requests-v1",
            str(actor_id),
            box.value,
            view.value,
        ):
            raise InvalidRequestCursorError
        cursor = RequestCursor(
            datetime.fromisoformat(anchor), datetime.fromisoformat(sent), UUID(request_id)
        )
        if cursor.as_of > now or encode_request_cursor(actor_id, box, view, cursor) != encoded:
            raise InvalidRequestCursorError
        return cursor
    except (ValueError, UnicodeError, binascii.Error):
        raise InvalidRequestCursorError from None
