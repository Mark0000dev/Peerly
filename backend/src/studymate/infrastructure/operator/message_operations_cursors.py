from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.message_operations_ports import OperatorMessageOperationPosition
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

OPERATION_CURSOR_PARTS = 7


@dataclass(frozen=True, slots=True)
class FernetOperatorMessageOperationCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorMessageOperationCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Message operations require the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.message-operations.v1")))

    def encode_operations(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        position: OperatorMessageOperationPosition,
    ) -> str:
        return encode_cursor(
            self.cipher,
            (
                "operator-message-operations-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                position.terminal_at.isoformat(),
                str(position.id),
                position.as_of.isoformat(),
            ),
        )

    def decode_operations(
        self, scope: OperatorCursorScope, account_id: UUID, token: str
    ) -> OperatorMessageOperationPosition:
        version, actor, grant, target, timestamp, identity, as_of = cursor_payload(
            self.cipher, token, OPERATION_CURSOR_PARTS
        )
        if (version, actor, grant, target) != (
            "operator-message-operations-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorMessageOperationPosition(
                datetime.fromisoformat(timestamp), UUID(identity), datetime.fromisoformat(as_of)
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
        if (position.terminal_at.isoformat(), str(position.id), position.as_of.isoformat()) != (
            timestamp,
            identity,
            as_of,
        ):
            raise InvalidOperatorCursorError
        return position
