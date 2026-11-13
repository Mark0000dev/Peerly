"""Opaque issuance keyset, bound to actor, current grant and target account."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.session_history_ports import SessionHistoryPosition
from studymate.domain.time import require_aware
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

CURSOR_PARTS = 7


@dataclass(frozen=True, slots=True)
class FernetOperatorSessionHistoryCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorSessionHistoryCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Session history requires the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.session-history.v1")))

    def encode_history(
        self, scope: OperatorCursorScope, target_id: UUID, position: SessionHistoryPosition
    ) -> str:
        return encode_cursor(
            self.cipher,
            (
                "operator-session-history-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(target_id),
                position.as_of.astimezone(UTC).isoformat(),
                position.issued_at.astimezone(UTC).isoformat(),
                str(position.session_id),
            ),
        )

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str, now: datetime
    ) -> SessionHistoryPosition:
        require_aware(now)
        version, actor, grant, target, anchor, created, challenge = cursor_payload(
            self.cipher, token, CURSOR_PARTS
        )
        if (version, actor, grant, target) != (
            "operator-session-history-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(target_id),
        ):
            raise InvalidOperatorCursorError
        try:
            position = SessionHistoryPosition(
                datetime.fromisoformat(anchor), datetime.fromisoformat(created), UUID(challenge)
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
        if position.as_of > now or (anchor, created, challenge) != (
            position.as_of.astimezone(UTC).isoformat(),
            position.issued_at.astimezone(UTC).isoformat(),
            str(position.session_id),
        ):
            raise InvalidOperatorCursorError
        return position
