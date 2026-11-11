"""Independent actor/grant/account/version-bound opaque history cursor, not authority."""

from dataclasses import dataclass, field
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.help_history_ports import OperatorHelpHistoryPosition
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

HISTORY_CURSOR_PARTS = 6


@dataclass(frozen=True, slots=True)
class FernetOperatorHelpHistoryCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorHelpHistoryCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Help history requires the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.help-history.v1")))

    def encode_history(
        self, scope: OperatorCursorScope, target_id: UUID, position: OperatorHelpHistoryPosition
    ) -> str:
        return encode_cursor(
            self.cipher,
            (
                "operator-help-history-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(target_id),
                str(position.anchor_version),
                str(position.before_version),
            ),
        )

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str
    ) -> OperatorHelpHistoryPosition:
        version, actor, grant, target, anchor, before = cursor_payload(
            self.cipher, token, HISTORY_CURSOR_PARTS
        )
        if (version, actor, grant, target) != (
            "operator-help-history-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(target_id),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorHelpHistoryPosition(int(anchor), int(before))
        except ValueError:
            raise InvalidOperatorCursorError from None
        if (str(position.anchor_version), str(position.before_version)) != (anchor, before):
            raise InvalidOperatorCursorError
        return position
