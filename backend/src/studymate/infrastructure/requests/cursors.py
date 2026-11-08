import base64
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from studymate.application.requests.cursors import (
    CURSOR_LIMIT,
    InvalidRequestCursorError,
    RequestCursor,
    decode_request_cursor,
    encode_request_cursor,
)
from studymate.domain.requests.projections import RequestBox, RequestListView

KEY_BYTES = 32


@dataclass(frozen=True, slots=True)
class FernetRequestCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetRequestCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Request cursors require the configured32-byte envelope key")
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=None,
            info=b"peerly.requests.cursor.v1",
        ).derive(envelope_key)
        return cls(Fernet(base64.urlsafe_b64encode(key)))

    def encode(
        self, actor_id: UUID, box: RequestBox, view: RequestListView, cursor: RequestCursor
    ) -> str:
        return self.cipher.encrypt(
            encode_request_cursor(actor_id, box, view, cursor).encode("ascii")
        ).decode("ascii")

    def decode(
        self, actor_id: UUID, box: RequestBox, view: RequestListView, token: str, now: datetime
    ) -> RequestCursor:
        if len(token) > CURSOR_LIMIT:
            raise InvalidRequestCursorError
        try:
            payload = self.cipher.decrypt(token.encode("ascii")).decode("ascii")
        except (InvalidToken, UnicodeError):
            raise InvalidRequestCursorError from None
        return decode_request_cursor(actor_id, box, view, payload, now)
