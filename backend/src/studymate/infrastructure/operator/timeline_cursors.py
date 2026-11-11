"""Purpose-separated opaque event search cursor; never a role or commit watermark."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.timeline_ports import OperatorEventPosition
from studymate.domain.time import require_aware
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

EVENT_PARTS = 7


@dataclass(frozen=True, slots=True)
class FernetOperatorEventCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorEventCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Operator event search requires the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.event-search.v1")))

    def encode_events(
        self, scope: OperatorCursorScope, fingerprint: bytes, position: OperatorEventPosition
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Operator event search requires its actual query HMAC")
        return encode_cursor(
            self.cipher,
            (
                "operator-events-v1",
                str(scope.account_id),
                str(scope.access_version),
                fingerprint.hex(),
                position.anchor_at.astimezone(UTC).isoformat(),
                position.occurred_at.astimezone(UTC).isoformat(),
                str(position.event_id),
            ),
        )

    def decode_events(
        self, scope: OperatorCursorScope, fingerprint: bytes, token: str, now: datetime
    ) -> OperatorEventPosition:
        require_aware(now)
        version, actor, grant, query, anchor, occurred, event_id = cursor_payload(
            self.cipher, token, EVENT_PARTS
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, query) != (
            "operator-events-v1",
            str(scope.account_id),
            str(scope.access_version),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorEventPosition(
                datetime.fromisoformat(anchor), datetime.fromisoformat(occurred), UUID(event_id)
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
        if position.anchor_at > now:
            raise InvalidOperatorCursorError
        return position
