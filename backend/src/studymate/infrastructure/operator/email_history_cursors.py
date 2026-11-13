"""Opaque creation keyset, bound to actor, current grant and target account."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.email_history_ports import EmailHistoryPosition
from studymate.domain.time import require_aware
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

CURSOR_PARTS = 7


@dataclass(frozen=True, slots=True)
class FernetOperatorEmailHistoryCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorEmailHistoryCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Email history requires the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.email-history.v1")))

    def encode_history(
        self, scope: OperatorCursorScope, target_id: UUID, position: EmailHistoryPosition
    ) -> str:
        return encode_cursor(
            self.cipher,
            (
                "operator-email-history-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(target_id),
                position.as_of.astimezone(UTC).isoformat(),
                position.created_at.astimezone(UTC).isoformat(),
                str(position.challenge_id),
            ),
        )

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str, now: datetime
    ) -> EmailHistoryPosition:
        require_aware(now)
        version, actor, grant, target, anchor, created, challenge = cursor_payload(
            self.cipher, token, CURSOR_PARTS
        )
        if (version, actor, grant, target) != (
            "operator-email-history-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(target_id),
        ):
            raise InvalidOperatorCursorError
        try:
            position = EmailHistoryPosition(
                datetime.fromisoformat(anchor), datetime.fromisoformat(created), UUID(challenge)
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
        if position.as_of > now or (anchor, created, challenge) != (
            position.as_of.astimezone(UTC).isoformat(),
            position.created_at.astimezone(UTC).isoformat(),
            str(position.challenge_id),
        ):
            raise InvalidOperatorCursorError
        return position
