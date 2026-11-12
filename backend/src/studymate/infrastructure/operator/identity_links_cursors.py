"""Purpose/actor/grant/target/claim-bound encrypted keyset cursor, never authority."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.identity_links_ports import OperatorIdentityLinksPosition
from studymate.domain.time import require_aware
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)


@dataclass(frozen=True, slots=True)
class FernetOperatorIdentityLinksCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorIdentityLinksCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Identity links require the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.identity-links.v1")))

    def encode_links(
        self,
        scope: OperatorCursorScope,
        target_id: UUID,
        fingerprint: bytes,
        position: OperatorIdentityLinksPosition,
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Identity links require the actual source fingerprint")
        return encode_cursor(
            self.cipher,
            (
                "operator-identity-links-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(target_id),
                fingerprint.hex(),
                position.as_of.astimezone(UTC).isoformat(),
                position.before_created_at.astimezone(UTC).isoformat(),
                str(position.before_account_id),
            ),
        )

    def decode_links(
        self,
        scope: OperatorCursorScope,
        target_id: UUID,
        fingerprint: bytes,
        token: str,
        now: datetime,
    ) -> OperatorIdentityLinksPosition:
        require_aware(now)
        version, actor, grant, target, source, anchor, created, account = cursor_payload(
            self.cipher, token, 8
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, target, source) != (
            "operator-identity-links-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(target_id),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorIdentityLinksPosition(
                datetime.fromisoformat(anchor), datetime.fromisoformat(created), UUID(account)
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
        if position.as_of > now or (
            position.as_of.astimezone(UTC).isoformat(),
            position.before_created_at.astimezone(UTC).isoformat(),
            str(position.before_account_id),
        ) != (anchor, created, account):
            raise InvalidOperatorCursorError
        return position
