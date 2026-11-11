"""Opaque source pagination bound to actual grant and closed query fingerprint."""

from dataclasses import dataclass, field
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

CURSOR_PARTS = 5


@dataclass(frozen=True, slots=True)
class FernetSourceCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, key: bytes) -> "FernetSourceCursorCodec":
        if len(key) != KEY_BYTES:
            raise ValueError("Source cursor requires the actual envelope key")
        return cls(Fernet(cursor_key(key, b"peerly.operator.delivery-sources.v1")))

    def encode(self, scope: OperatorCursorScope, fingerprint: bytes, before_id: UUID) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Source cursor requires its actual query fingerprint")
        return encode_cursor(
            self.cipher,
            (
                "delivery-sources-v1",
                str(scope.account_id),
                str(scope.access_version),
                fingerprint.hex(),
                str(before_id),
            ),
        )

    def decode(self, scope: OperatorCursorScope, fingerprint: bytes, token: str) -> UUID:
        version, actor, grant, query, before = cursor_payload(self.cipher, token, CURSOR_PARTS)
        if (version, actor, grant, query) != (
            "delivery-sources-v1",
            str(scope.account_id),
            str(scope.access_version),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            return UUID(before)
        except ValueError:
            raise InvalidOperatorCursorError from None
