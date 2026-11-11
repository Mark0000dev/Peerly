"""Distinct chat image root/filter and owned revision cursor purposes; never role authority."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.chat_image_ports import (
    OperatorChatImageHistoryPosition,
    OperatorChatImageUploadRootPosition,
)
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

ROOT_CURSOR_PARTS = 9
HISTORY_CURSOR_PARTS = 7


@dataclass(frozen=True, slots=True)
class FernetOperatorChatImageCursorCodec:
    roots: Fernet = field(repr=False)
    history: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorChatImageCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Chat image inspection needs the configured32-byte envelope key")
        return cls(
            Fernet(cursor_key(envelope_key, b"peerly.operator.chat-image-roots.v1")),
            Fernet(cursor_key(envelope_key, b"peerly.operator.chat-image-history.v1")),
        )

    def encode_roots(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorChatImageUploadRootPosition,
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Chat image roots require the actual query HMAC")
        return encode_cursor(
            self.roots,
            (
                "operator-chat-image-roots-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                fingerprint.hex(),
                position.anchor_created_at.isoformat(),
                str(position.anchor_image_id),
                position.before_created_at.isoformat(),
                str(position.before_image_id),
            ),
        )

    def decode_roots(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorChatImageUploadRootPosition:
        version, actor, grant, account, digest, anchor_at, anchor_image, before_at, before_image = (
            cursor_payload(self.roots, token, ROOT_CURSOR_PARTS)
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, account, digest) != (
            "operator-chat-image-roots-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            return OperatorChatImageUploadRootPosition(
                datetime.fromisoformat(anchor_at),
                UUID(anchor_image),
                datetime.fromisoformat(before_at),
                UUID(before_image),
            )
        except ValueError:
            raise InvalidOperatorCursorError from None

    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        image_id: UUID,
        position: OperatorChatImageHistoryPosition,
    ) -> str:
        return encode_cursor(
            self.history,
            (
                "operator-chat-image-history-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                str(image_id),
                str(position.anchor_version),
                str(position.before_version),
            ),
        )

    def decode_history(
        self, scope: OperatorCursorScope, account_id: UUID, image_id: UUID, token: str
    ) -> OperatorChatImageHistoryPosition:
        version, actor, grant, account, image, anchor, before = cursor_payload(
            self.history, token, HISTORY_CURSOR_PARTS
        )
        if (version, actor, grant, account, image) != (
            "operator-chat-image-history-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            str(image_id),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorChatImageHistoryPosition(int(anchor), int(before))
        except ValueError:
            raise InvalidOperatorCursorError from None
        if (str(position.anchor_version), str(position.before_version)) != (anchor, before):
            raise InvalidOperatorCursorError
        return position
