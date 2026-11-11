import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from studymate.domain.discovery_context import DiscoveryContext
from studymate.domain.discovery_order import DiscoveryPosition
from studymate.domain.time import require_aware

CURSOR_PARTS = 11


class DiscoveryView(StrEnum):
    CANDIDATES = "candidates"
    PASSED = "passed"


class InvalidDiscoveryCursorError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class DiscoveryCursor:
    as_of: datetime
    position: DiscoveryPosition

    def __post_init__(self) -> None:
        require_aware(self.as_of)


class DiscoveryCursorCodec(Protocol):
    def encode(
        self, context: DiscoveryContext, view: DiscoveryView, cursor: DiscoveryCursor
    ) -> str: ...

    def decode(
        self, context: DiscoveryContext, view: DiscoveryView, token: str, now: datetime
    ) -> DiscoveryCursor: ...


def encode_discovery_cursor(
    context: DiscoveryContext, view: DiscoveryView, cursor: DiscoveryCursor
) -> str:
    payload = json.dumps(
        (
            "discovery-v1",
            str(context.account_id),
            context.mode.value,
            str(context.goal_id) if context.goal_id is not None else "",
            str(context.goal_version) if context.goal_version is not None else "",
            str(context.help_version) if context.help_version is not None else "",
            view.value,
            cursor.as_of.astimezone(UTC).isoformat(),
            "1" if cursor.position.same_topic else "0",
            str(cursor.position.freshness),
            str(cursor.position.person_id),
        ),
        separators=(",", ":"),
    ).encode("ascii")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_discovery_cursor(
    context: DiscoveryContext, view: DiscoveryView, encoded: str, now: datetime
) -> DiscoveryCursor:
    require_aware(now)
    if re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", encoded) is None:
        raise InvalidDiscoveryCursorError
    try:
        payload: object = json.loads(
            base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        )
        if not isinstance(payload, list):
            raise InvalidDiscoveryCursorError
        strings = tuple(value for value in payload if isinstance(value, str))
        if len(strings) != CURSOR_PARTS or len(strings) != len(payload):
            raise InvalidDiscoveryCursorError
        if strings[-3] not in {"0", "1"}:
            raise InvalidDiscoveryCursorError
        cursor = DiscoveryCursor(
            datetime.fromisoformat(strings[-4]),
            DiscoveryPosition(strings[-3] == "1", int(strings[-2]), UUID(strings[-1])),
        )
        if cursor.as_of > now or encode_discovery_cursor(context, view, cursor) != encoded:
            raise InvalidDiscoveryCursorError
        return cursor
    except (ValueError, UnicodeError, binascii.Error):
        raise InvalidDiscoveryCursorError from None
