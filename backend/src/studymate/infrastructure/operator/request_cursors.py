"""Distinct request root/filter and owned revision cursor purposes; never role authority."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.request_ports import (
    OperatorRequestHistoryPosition,
    OperatorRequestPosition,
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
class FernetOperatorRequestCursorCodec:
    roots: Fernet = field(repr=False)
    history: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorRequestCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Request inspection needs the configured32-byte envelope key")
        return cls(
            Fernet(cursor_key(envelope_key, b"peerly.operator.connection-requests.v1")),
            Fernet(cursor_key(envelope_key, b"peerly.operator.connection-request-history.v1")),
        )

    def encode_roots(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorRequestPosition,
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Request roots require the actual query HMAC")
        return encode_cursor(
            self.roots,
            (
                "operator-connection-requests-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                fingerprint.hex(),
                position.anchor_sent_at.isoformat(),
                str(position.anchor_request_id),
                position.before_sent_at.isoformat(),
                str(position.before_request_id),
            ),
        )

    def decode_roots(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorRequestPosition:
        (
            version,
            actor,
            grant,
            account,
            digest,
            anchor_at,
            anchor_request,
            before_at,
            before_request,
        ) = cursor_payload(self.roots, token, ROOT_CURSOR_PARTS)
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, account, digest) != (
            "operator-connection-requests-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            return OperatorRequestPosition(
                datetime.fromisoformat(anchor_at),
                UUID(anchor_request),
                datetime.fromisoformat(before_at),
                UUID(before_request),
            )
        except ValueError:
            raise InvalidOperatorCursorError from None

    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        request_id: UUID,
        position: OperatorRequestHistoryPosition,
    ) -> str:
        return encode_cursor(
            self.history,
            (
                "operator-connection-request-history-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                str(request_id),
                str(position.anchor_version),
                str(position.before_version),
            ),
        )

    def decode_history(
        self, scope: OperatorCursorScope, account_id: UUID, request_id: UUID, token: str
    ) -> OperatorRequestHistoryPosition:
        version, actor, grant, account, request, anchor, before = cursor_payload(
            self.history, token, HISTORY_CURSOR_PARTS
        )
        if (version, actor, grant, account, request) != (
            "operator-connection-request-history-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            str(request_id),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorRequestHistoryPosition(int(anchor), int(before))
        except ValueError:
            raise InvalidOperatorCursorError from None
        if (str(position.anchor_version), str(position.before_version)) != (anchor, before):
            raise InvalidOperatorCursorError
        return position
