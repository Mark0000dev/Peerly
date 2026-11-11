"""Distinct photo root/filter and owned revision cursor purposes; never role authority."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.photo_ports import (
    OperatorPhotoHistoryPosition,
    OperatorPhotoUploadRootPosition,
)
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

ROOT_CURSOR_PARTS = 9
HISTORY_CURSOR_PARTS = 7


@dataclass(frozen=True, slots=True)
class FernetOperatorPhotoCursorCodec:
    roots: Fernet = field(repr=False)
    history: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorPhotoCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Photo inspection needs the configured32-byte envelope key")
        return cls(
            Fernet(cursor_key(envelope_key, b"peerly.operator.photo-roots.v1")),
            Fernet(cursor_key(envelope_key, b"peerly.operator.photo-history.v1")),
        )

    def encode_roots(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorPhotoUploadRootPosition,
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Photo roots require the actual query HMAC")
        return encode_cursor(
            self.roots,
            (
                "operator-photo-roots-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                fingerprint.hex(),
                position.anchor_created_at.isoformat(),
                str(position.anchor_upload_id),
                position.before_created_at.isoformat(),
                str(position.before_upload_id),
            ),
        )

    def decode_roots(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorPhotoUploadRootPosition:
        version, actor, grant, account, digest, anchor_at, anchor_photo, before_at, before_photo = (
            cursor_payload(self.roots, token, ROOT_CURSOR_PARTS)
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, account, digest) != (
            "operator-photo-roots-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            return OperatorPhotoUploadRootPosition(
                datetime.fromisoformat(anchor_at),
                UUID(anchor_photo),
                datetime.fromisoformat(before_at),
                UUID(before_photo),
            )
        except ValueError:
            raise InvalidOperatorCursorError from None

    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        upload_id: UUID,
        position: OperatorPhotoHistoryPosition,
    ) -> str:
        return encode_cursor(
            self.history,
            (
                "operator-photo-history-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                str(upload_id),
                str(position.anchor_version),
                str(position.before_version),
            ),
        )

    def decode_history(
        self, scope: OperatorCursorScope, account_id: UUID, upload_id: UUID, token: str
    ) -> OperatorPhotoHistoryPosition:
        version, actor, grant, account, photo, anchor, before = cursor_payload(
            self.history, token, HISTORY_CURSOR_PARTS
        )
        if (version, actor, grant, account, photo) != (
            "operator-photo-history-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            str(upload_id),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorPhotoHistoryPosition(int(anchor), int(before))
        except ValueError:
            raise InvalidOperatorCursorError from None
        if (str(position.anchor_version), str(position.before_version)) != (anchor, before):
            raise InvalidOperatorCursorError
        return position
