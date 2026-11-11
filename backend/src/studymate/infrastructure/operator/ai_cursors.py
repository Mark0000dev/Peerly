"""Account/filter/active-grant bound retained AI metadata cursor, never role authority."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.ai_ports import (
    OperatorAiPosition,
)
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

ROOT_CURSOR_PARTS = 9


@dataclass(frozen=True, slots=True)
class FernetOperatorAiCursorCodec:
    roots: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorAiCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("AI inspection needs the configured32-byte envelope key")
        return cls(
            Fernet(cursor_key(envelope_key, b"peerly.operator.ai-jobs.v1")),
        )

    def encode(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorAiPosition,
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("AI roots require the actual query HMAC")
        return encode_cursor(
            self.roots,
            (
                "operator-ai-jobs-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                fingerprint.hex(),
                position.anchor_created_at.isoformat(),
                str(position.anchor_job_id),
                position.before_created_at.isoformat(),
                str(position.before_job_id),
            ),
        )

    def decode(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorAiPosition:
        version, actor, grant, account, digest, anchor_at, anchor_job, before_at, before_job = (
            cursor_payload(self.roots, token, ROOT_CURSOR_PARTS)
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, account, digest) != (
            "operator-ai-jobs-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            return OperatorAiPosition(
                datetime.fromisoformat(anchor_at),
                UUID(anchor_job),
                datetime.fromisoformat(before_at),
                UUID(before_job),
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
