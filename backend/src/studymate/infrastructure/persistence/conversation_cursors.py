"""Opaque actor-bound thread keysets, purpose-separated from all other cursors."""

import base64
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from studymate.application.messaging.conversation_list import (
    CONVERSATION_CURSOR_LIMIT,
    ConversationListCursor,
    InvalidConversationCursorError,
)
from studymate.domain.time import require_aware

KEY_BYTES = 32
CURSOR_FIELDS = 5
CURSOR_LIFETIME = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class FernetConversationListCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetConversationListCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Conversation cursors require a32-byte envelope key")
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=None,
            info=b"peerly.conversations.cursor.v1",
        ).derive(envelope_key)
        return cls(Fernet(base64.urlsafe_b64encode(key)))

    def encode(self, actor_id: UUID, value: ConversationListCursor) -> str:
        payload = json.dumps(
            (
                "conversations-v1",
                str(actor_id),
                value.as_of.astimezone(UTC).isoformat(),
                value.activity_at.astimezone(UTC).isoformat(),
                str(value.conversation_id),
            ),
            separators=(",", ":"),
        )
        return self.cipher.encrypt(payload.encode("ascii")).decode("ascii")

    def decode(self, actor_id: UUID, token: str, now: datetime) -> ConversationListCursor:
        require_aware(now)
        if not 1 <= len(token) <= CONVERSATION_CURSOR_LIMIT:
            raise InvalidConversationCursorError
        try:
            data: object = json.loads(self.cipher.decrypt(token.encode("ascii")))
            if (
                not isinstance(data, list)
                or len(data) != CURSOR_FIELDS
                or not all(isinstance(value, str) for value in data)
            ):
                raise InvalidConversationCursorError
            version, actor, anchor, activity, identifier = tuple(
                value for value in data if isinstance(value, str)
            )
            if version != "conversations-v1" or actor != str(actor_id):
                raise InvalidConversationCursorError
            cursor = ConversationListCursor(
                datetime.fromisoformat(anchor),
                datetime.fromisoformat(activity),
                UUID(identifier),
            )
            if cursor.as_of > now or now - cursor.as_of > CURSOR_LIFETIME:
                raise InvalidConversationCursorError
            return cursor
        except (InvalidToken, ValueError, UnicodeError):
            raise InvalidConversationCursorError from None
