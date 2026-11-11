import base64
from dataclasses import dataclass, field
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from studymate.application.messaging.goal_shares import (
    MAX_GOAL_SHARE_CURSOR_LENGTH,
    GoalShareCursor,
    InvalidGoalShareCursorError,
    decode_goal_share_cursor,
    encode_goal_share_cursor,
)

KEY_BYTES = 32


@dataclass(frozen=True, slots=True)
class FernetGoalShareCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetGoalShareCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Goal history requires the configured32-byte envelope key")
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=None,
            info=b"peerly.messaging.goal-share-cursor.v1",
        ).derive(envelope_key)
        return cls(Fernet(base64.urlsafe_b64encode(key)))

    def encode(self, actor_id: UUID, conversation_id: UUID, cursor: GoalShareCursor) -> str:
        return self.cipher.encrypt(
            encode_goal_share_cursor(actor_id, conversation_id, cursor).encode("ascii")
        ).decode("ascii")

    def decode(self, actor_id: UUID, conversation_id: UUID, token: str) -> GoalShareCursor:
        if len(token) > MAX_GOAL_SHARE_CURSOR_LENGTH:
            raise InvalidGoalShareCursorError
        try:
            payload = self.cipher.decrypt(token.encode("ascii")).decode("ascii")
        except (InvalidToken, UnicodeError):
            raise InvalidGoalShareCursorError from None
        return decode_goal_share_cursor(actor_id, conversation_id, payload)
