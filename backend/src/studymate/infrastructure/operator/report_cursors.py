"""Purpose-separated report metadata search cursor, never an access or commit token."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.report_ports import OperatorReportPosition
from studymate.domain.time import require_aware
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

REPORT_PARTS = 7


@dataclass(frozen=True, slots=True)
class FernetOperatorReportCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorReportCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Operator report search requires the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.report-search.v1")))

    def encode_reports(
        self, scope: OperatorCursorScope, fingerprint: bytes, position: OperatorReportPosition
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Operator report search requires its actual query HMAC")
        return encode_cursor(
            self.cipher,
            (
                "operator-reports-v1",
                str(scope.account_id),
                str(scope.access_version),
                fingerprint.hex(),
                position.anchor_at.astimezone(UTC).isoformat(),
                position.submitted_at.astimezone(UTC).isoformat(),
                str(position.report_id),
            ),
        )

    def decode_reports(
        self, scope: OperatorCursorScope, fingerprint: bytes, token: str, now: datetime
    ) -> OperatorReportPosition:
        require_aware(now)
        version, actor, grant, query, anchor, submitted, report = cursor_payload(
            self.cipher, token, REPORT_PARTS
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, query) != (
            "operator-reports-v1",
            str(scope.account_id),
            str(scope.access_version),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorReportPosition(
                datetime.fromisoformat(anchor), datetime.fromisoformat(submitted), UUID(report)
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
        if position.anchor_at > now:
            raise InvalidOperatorCursorError
        return position
