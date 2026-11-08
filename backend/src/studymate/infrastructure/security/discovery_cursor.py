import base64
from dataclasses import dataclass, field
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from studymate.application.discovery.cursors import (
    DiscoveryCursor,
    DiscoveryView,
    InvalidDiscoveryCursorError,
    decode_discovery_cursor,
    encode_discovery_cursor,
)
from studymate.domain.discovery_context import DiscoveryContext

KEY_BYTES = 32
TOKEN_LIMIT = 1024


@dataclass(frozen=True, slots=True)
class FernetDiscoveryCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetDiscoveryCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Discovery cursor requires the configured 32-byte envelope key")
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=None,
            info=b"peerly.discovery.cursor.v1",
        ).derive(envelope_key)
        return cls(Fernet(base64.urlsafe_b64encode(key)))

    def encode(
        self, context: DiscoveryContext, view: DiscoveryView, cursor: DiscoveryCursor
    ) -> str:
        payload = encode_discovery_cursor(context, view, cursor).encode("ascii")
        return self.cipher.encrypt(payload).decode("ascii")

    def decode(
        self, context: DiscoveryContext, view: DiscoveryView, token: str, now: datetime
    ) -> DiscoveryCursor:
        if len(token) > TOKEN_LIMIT:
            raise InvalidDiscoveryCursorError
        try:
            payload = self.cipher.decrypt(token.encode("ascii")).decode("ascii")
        except (InvalidToken, UnicodeError):
            raise InvalidDiscoveryCursorError from None
        return decode_discovery_cursor(context, view, payload, now)
