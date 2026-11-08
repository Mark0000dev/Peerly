import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

MAX_MESSAGE_SEQUENCE = (1 << 63) - 1
MAX_HISTORY_CURSOR_LENGTH = 1024
HISTORY_CURSOR_PARTS = 5


class InvalidMessageHistoryCursorError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class MessageHistoryCursor:
    anchor_sequence: int
    before_sequence: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_MESSAGE_SEQUENCE
                for value in (self.anchor_sequence, self.before_sequence)
            )
            or self.before_sequence > self.anchor_sequence
        ):
            raise ValueError("History cursor requires bounded committed server sequences")


class MessageHistoryCursorCodec(Protocol):
    def encode(
        self, actor_id: UUID, conversation_id: UUID, cursor: MessageHistoryCursor
    ) -> str: ...

    def decode(self, actor_id: UUID, conversation_id: UUID, token: str) -> MessageHistoryCursor: ...


def encode_history_cursor(
    actor_id: UUID, conversation_id: UUID, cursor: MessageHistoryCursor
) -> str:
    return json.dumps(
        (
            "messages-v1",
            str(actor_id),
            str(conversation_id),
            str(cursor.anchor_sequence),
            str(cursor.before_sequence),
        ),
        separators=(",", ":"),
    )


def decode_history_cursor(
    actor_id: UUID, conversation_id: UUID, payload: str
) -> MessageHistoryCursor:
    if len(payload) > MAX_HISTORY_CURSOR_LENGTH:
        raise InvalidMessageHistoryCursorError
    try:
        parsed: object = json.loads(payload)
        if not isinstance(parsed, list):
            raise InvalidMessageHistoryCursorError
        parts = tuple(value for value in parsed if isinstance(value, str))
        if len(parts) != HISTORY_CURSOR_PARTS or len(parts) != len(parsed):
            raise InvalidMessageHistoryCursorError
        version, actor, conversation, anchor, before = parts
        if (version, actor, conversation) != ("messages-v1", str(actor_id), str(conversation_id)):
            raise InvalidMessageHistoryCursorError
        cursor = MessageHistoryCursor(int(anchor), int(before))
        if encode_history_cursor(actor_id, conversation_id, cursor) != payload:
            raise InvalidMessageHistoryCursorError
        return cursor
    except (ValueError, UnicodeError):
        raise InvalidMessageHistoryCursorError from None
