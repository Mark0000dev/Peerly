"""Purpose-separated opaque audit search cursor; never a role or commit watermark."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.audit_search_ports import OperatorAuditPosition
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.time import require_aware
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

AUDIT_PARTS = 7


@dataclass(frozen=True, slots=True)
class FernetOperatorAuditCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorAuditCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Operator audit search requires the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.audit-search.v1")))

    def encode_audits(
        self, scope: OperatorCursorScope, fingerprint: bytes, position: OperatorAuditPosition
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Operator audit search requires its actual query HMAC")
        return encode_cursor(
            self.cipher,
            (
                "operator-audits-v1",
                str(scope.account_id),
                str(scope.access_version),
                fingerprint.hex(),
                position.anchor_at.astimezone(UTC).isoformat(),
                position.occurred_at.astimezone(UTC).isoformat(),
                str(position.audit_id),
            ),
        )

    def decode_audits(
        self, scope: OperatorCursorScope, fingerprint: bytes, token: str, now: datetime
    ) -> OperatorAuditPosition:
        require_aware(now)
        version, actor, grant, query, anchor, occurred, audit_id = cursor_payload(
            self.cipher, token, AUDIT_PARTS
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, query) != (
            "operator-audits-v1",
            str(scope.account_id),
            str(scope.access_version),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorAuditPosition(
                datetime.fromisoformat(anchor), datetime.fromisoformat(occurred), UUID(audit_id)
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
        if position.anchor_at > now:
            raise InvalidOperatorCursorError
        return position
