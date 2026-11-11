"""Local opaque pagination, never an operator grant; DB authority is checked separately."""

import base64
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.ports import OperatorAccountPosition, OperatorMessagePosition
from studymate.domain.time import require_aware

KEY_BYTES = 32
CURSOR_LIMIT = 1024
ACCOUNT_PARTS = 7
MESSAGE_PARTS = 6


def cursor_key(envelope_key: bytes, purpose: bytes) -> bytes:
    return base64.urlsafe_b64encode(
        HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=None, info=purpose).derive(
            envelope_key
        )
    )


def cursor_payload(cipher: Fernet, token: str, length: int) -> tuple[str, ...]:
    if len(token) > CURSOR_LIMIT:
        raise InvalidOperatorCursorError
    try:
        decoded: object = json.loads(cipher.decrypt(token.encode("ascii")).decode("ascii"))
    except (ValueError, UnicodeError, InvalidToken):
        raise InvalidOperatorCursorError from None
    if not isinstance(decoded, list):
        raise InvalidOperatorCursorError
    parts = tuple(value for value in decoded if isinstance(value, str))
    if len(parts) != length or len(parts) != len(decoded):
        raise InvalidOperatorCursorError
    return parts


def encode_cursor(cipher: Fernet, parts: tuple[str, ...]) -> str:
    return cipher.encrypt(json.dumps(parts, separators=(",", ":")).encode("ascii")).decode("ascii")


@dataclass(frozen=True, slots=True)
class FernetOperatorCursorCodec:
    accounts: Fernet = field(repr=False)
    messages: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Operator pagination requires the configured32-byte envelope key")
        return cls(
            Fernet(cursor_key(envelope_key, b"peerly.operator.account-search.v1")),
            Fernet(cursor_key(envelope_key, b"peerly.operator.messages.v1")),
        )

    def encode_accounts(
        self,
        scope: OperatorCursorScope,
        filters_fingerprint: bytes,
        position: OperatorAccountPosition,
    ) -> str:
        if len(filters_fingerprint) != KEY_BYTES:
            raise ValueError("Operator search scope requires the actual query HMAC")
        return encode_cursor(
            self.accounts,
            (
                "operator-accounts-v1",
                str(scope.account_id),
                str(scope.access_version),
                filters_fingerprint.hex(),
                position.as_of.astimezone(UTC).isoformat(),
                position.created_at.astimezone(UTC).isoformat(),
                str(position.account_id),
            ),
        )

    def decode_accounts(
        self, scope: OperatorCursorScope, filters_fingerprint: bytes, token: str, now: datetime
    ) -> OperatorAccountPosition:
        require_aware(now)
        version, actor, grant, fingerprint, anchor, created, account = cursor_payload(
            self.accounts, token, ACCOUNT_PARTS
        )
        if len(filters_fingerprint) != KEY_BYTES or (version, actor, grant, fingerprint) != (
            "operator-accounts-v1",
            str(scope.account_id),
            str(scope.access_version),
            filters_fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorAccountPosition(
                datetime.fromisoformat(anchor), datetime.fromisoformat(created), UUID(account)
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
        if position.as_of > now:
            raise InvalidOperatorCursorError
        return position

    def encode_messages(
        self, scope: OperatorCursorScope, conversation_id: UUID, position: OperatorMessagePosition
    ) -> str:
        return encode_cursor(
            self.messages,
            (
                "operator-messages-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(conversation_id),
                str(position.anchor_sequence),
                str(position.before_sequence),
            ),
        )

    def decode_messages(
        self, scope: OperatorCursorScope, conversation_id: UUID, token: str
    ) -> OperatorMessagePosition:
        version, actor, grant, conversation, anchor, before = cursor_payload(
            self.messages, token, MESSAGE_PARTS
        )
        if (version, actor, grant, conversation) != (
            "operator-messages-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(conversation_id),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorMessagePosition(int(anchor), int(before))
        except ValueError:
            raise InvalidOperatorCursorError from None
        if (str(position.anchor_sequence), str(position.before_sequence)) != (anchor, before):
            raise InvalidOperatorCursorError
        return position
