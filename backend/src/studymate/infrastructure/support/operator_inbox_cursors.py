"""Purpose-separated operator/grant/case/query-bound cursors, never grants."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.support.operator_inbox_ports import (
    OperatorSupportHistoryPosition,
    OperatorSupportPosition,
)
from studymate.domain.time import require_aware
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

INBOX_PARTS = 7
HISTORY_PARTS = 6


@dataclass(frozen=True, slots=True)
class FernetOperatorSupportInboxCursorCodec:
    inbox: Fernet = field(repr=False)
    history: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorSupportInboxCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Support operator cursors require the configured32-byte envelope key")
        return cls(
            Fernet(cursor_key(envelope_key, b"peerly.operator.support-inbox.v1")),
            Fernet(cursor_key(envelope_key, b"peerly.operator.support-history.v1")),
        )

    def encode_inbox(
        self, scope: OperatorCursorScope, fingerprint: bytes, position: OperatorSupportPosition
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Support search requires its actual query HMAC")
        return encode_cursor(
            self.inbox,
            (
                "operator-support-inbox-v1",
                str(scope.account_id),
                str(scope.access_version),
                fingerprint.hex(),
                position.anchor_at.astimezone(UTC).isoformat(),
                position.received_at.astimezone(UTC).isoformat(),
                str(position.case_id),
            ),
        )

    def decode_inbox(
        self, scope: OperatorCursorScope, fingerprint: bytes, token: str, now: datetime
    ) -> OperatorSupportPosition:
        require_aware(now)
        version, actor, grant, query, anchor, received, case = cursor_payload(
            self.inbox, token, INBOX_PARTS
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, query) != (
            "operator-support-inbox-v1",
            str(scope.account_id),
            str(scope.access_version),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorSupportPosition(
                datetime.fromisoformat(anchor), datetime.fromisoformat(received), UUID(case)
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
        if position.anchor_at > now:
            raise InvalidOperatorCursorError
        return position

    def encode_history(
        self, scope: OperatorCursorScope, case_id: UUID, position: OperatorSupportHistoryPosition
    ) -> str:
        return encode_cursor(
            self.history,
            (
                "operator-support-history-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(case_id),
                str(position.anchor_version),
                str(position.before_version),
            ),
        )

    def decode_history(
        self, scope: OperatorCursorScope, case_id: UUID, token: str
    ) -> OperatorSupportHistoryPosition:
        version, actor, grant, case, anchor, before = cursor_payload(
            self.history, token, HISTORY_PARTS
        )
        if (version, actor, grant, case) != (
            "operator-support-history-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(case_id),
        ):
            raise InvalidOperatorCursorError
        try:
            return OperatorSupportHistoryPosition(int(anchor), int(before))
        except ValueError:
            raise InvalidOperatorCursorError from None
