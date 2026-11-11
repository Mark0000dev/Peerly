from dataclasses import dataclass, field
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.conversation_index_ports import OperatorConversationPosition
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

CONVERSATION_CURSOR_PARTS = 5


@dataclass(frozen=True, slots=True)
class FernetOperatorConversationCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorConversationCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Conversation index requires the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.conversation-index.v1")))

    def encode_conversations(
        self, scope: OperatorCursorScope, account_id: UUID, position: OperatorConversationPosition
    ) -> str:
        return encode_cursor(
            self.cipher,
            (
                "operator-conversations-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                str(position.before_id),
            ),
        )

    def decode_conversations(
        self, scope: OperatorCursorScope, account_id: UUID, token: str
    ) -> OperatorConversationPosition:
        version, actor, grant, target, before = cursor_payload(
            self.cipher, token, CONVERSATION_CURSOR_PARTS
        )
        if (version, actor, grant, target) != (
            "operator-conversations-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
        ):
            raise InvalidOperatorCursorError
        try:
            return OperatorConversationPosition(UUID(before))
        except ValueError:
            raise InvalidOperatorCursorError from None
