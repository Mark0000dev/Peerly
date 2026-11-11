import base64
from dataclasses import dataclass, field
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from studymate.application.messaging.history_cursors import (
    MAX_HISTORY_CURSOR_LENGTH,
    InvalidMessageHistoryCursorError,
    MessageHistoryCursor,
    decode_history_cursor,
    encode_history_cursor,
)

KEY_BYTES = 32


@dataclass(frozen=True, slots=True)
class FernetMessageHistoryCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetMessageHistoryCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Message history requires the configured32-byte envelope key")
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=None,
            info=b"peerly.messaging.history-cursor.v1",
        ).derive(envelope_key)
        return cls(Fernet(base64.urlsafe_b64encode(key)))

    def encode(self, actor_id: UUID, conversation_id: UUID, cursor: MessageHistoryCursor) -> str:
        return self.cipher.encrypt(
            encode_history_cursor(actor_id, conversation_id, cursor).encode("ascii")
        ).decode("ascii")

    def decode(self, actor_id: UUID, conversation_id: UUID, token: str) -> MessageHistoryCursor:
        if len(token) > MAX_HISTORY_CURSOR_LENGTH:
            raise InvalidMessageHistoryCursorError
        try:
            payload = self.cipher.decrypt(token.encode("ascii")).decode("ascii")
        except (InvalidToken, UnicodeError):
            raise InvalidMessageHistoryCursorError from None
        return decode_history_cursor(actor_id, conversation_id, payload)
