"""Encrypted disclosure metadata cursors with a dedicated purpose and bound query HMAC."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.disclosure_ports import OperatorDisclosurePosition
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

CURSOR_PARTS = 10
PURPOSE = "operator-request-disclosures-v1"


@dataclass(frozen=True, slots=True)
class FernetOperatorDisclosureCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorDisclosureCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Disclosure cursors require the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.request-disclosures.v1")))

    def encode(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        request_id: UUID,
        fingerprint: bytes,
        position: OperatorDisclosurePosition,
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Disclosure cursor requires the actual query HMAC")
        return encode_cursor(
            self.cipher,
            (
                PURPOSE,
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                str(request_id),
                fingerprint.hex(),
                position.anchor_created_at.isoformat(),
                str(position.anchor_disclosure_id),
                position.before_created_at.isoformat(),
                str(position.before_disclosure_id),
            ),
        )

    def decode(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        request_id: UUID,
        fingerprint: bytes,
        token: str,
    ) -> OperatorDisclosurePosition:
        version, actor, grant, account, request, digest, anchor_at, anchor, before_at, before = (
            cursor_payload(self.cipher, token, CURSOR_PARTS)
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, account, request, digest) != (
            PURPOSE,
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            str(request_id),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            return OperatorDisclosurePosition(
                datetime.fromisoformat(anchor_at),
                UUID(anchor),
                datetime.fromisoformat(before_at),
                UUID(before),
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
