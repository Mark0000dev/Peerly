from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.application.operator.report_triage_ports import InvalidReportTriageSourceError
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.report_triage import ReportTriageSourceClaims
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

TRIAGE_SOURCE_PARTS = 9


@dataclass(frozen=True, slots=True)
class FernetReportTriageSourceCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetReportTriageSourceCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Report triage requires the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.report-triage-source.v1")))

    def encode_source(self, claims: ReportTriageSourceClaims) -> str:
        return encode_cursor(
            self.cipher,
            (
                "report-triage-source-v1",
                str(claims.operator_id),
                str(claims.actor_session_id),
                str(claims.operator_access_version),
                str(claims.report_id),
                str(claims.review_version or 0),
                claims.evidence_digest.hex(),
                claims.issued_at.isoformat(),
                claims.expires_at.isoformat(),
            ),
        )

    def decode_source(
        self,
        token: str,
        access: OperatorAccess,
        actor_session_id: UUID,
        report_id: UUID,
        now: datetime,
    ) -> ReportTriageSourceClaims:
        try:
            version, actor, session, grant, report, review, digest, issued, expires = (
                cursor_payload(self.cipher, token, TRIAGE_SOURCE_PARTS)
            )
            if (version, actor, session, grant, report) != (
                "report-triage-source-v1",
                str(access.account_id),
                str(actor_session_id),
                str(access.version),
                str(report_id),
            ):
                raise InvalidReportTriageSourceError
            review_version = int(review)
            claims = ReportTriageSourceClaims(
                report_id,
                access.account_id,
                actor_session_id,
                access.version,
                review_version if review_version else None,
                bytes.fromhex(digest),
                datetime.fromisoformat(issued),
                datetime.fromisoformat(expires),
            )
            if (
                str(claims.review_version or 0),
                claims.evidence_digest.hex(),
                claims.issued_at.isoformat(),
                claims.expires_at.isoformat(),
            ) != (
                review,
                digest,
                issued,
                expires,
            ) or not claims.issued_at <= now < claims.expires_at:
                raise InvalidReportTriageSourceError
            return claims
        except (InvalidOperatorCursorError, ValueError):
            raise InvalidReportTriageSourceError from None
