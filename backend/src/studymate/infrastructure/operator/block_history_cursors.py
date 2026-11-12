from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.block_history_ports import OperatorBlockHistoryPosition
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.operator.block_history import OperatorBlockHistoryAnchors
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

BLOCK_HISTORY_CURSOR_PARTS = 12


@dataclass(frozen=True, slots=True)
class FernetOperatorBlockHistoryCursorCodec:
    cipher: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorBlockHistoryCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Block history requires the configured32-byte envelope key")
        return cls(Fernet(cursor_key(envelope_key, b"peerly.operator.block-history.v1")))

    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        relationship_id: UUID,
        pair: AccountPair,
        position: OperatorBlockHistoryPosition,
    ) -> str:
        position.validate_pair(pair)
        return encode_cursor(
            self.cipher,
            (
                "operator-block-history-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                str(relationship_id),
                str(pair.low),
                str(pair.high),
                str(position.anchors.low_version),
                str(position.anchors.high_version),
                position.changed_at.isoformat(),
                str(position.blocker_id),
                str(position.version),
            ),
        )

    def decode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        relationship_id: UUID,
        pair: AccountPair,
        token: str,
    ) -> OperatorBlockHistoryPosition:
        (
            marker,
            actor,
            grant,
            account,
            relationship,
            low,
            high,
            low_version,
            high_version,
            timestamp,
            blocker,
            version,
        ) = cursor_payload(self.cipher, token, BLOCK_HISTORY_CURSOR_PARTS)
        if (marker, actor, grant, account, relationship, low, high) != (
            "operator-block-history-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            str(relationship_id),
            str(pair.low),
            str(pair.high),
        ):
            raise InvalidOperatorCursorError
        try:
            anchors = OperatorBlockHistoryAnchors(int(low_version), int(high_version))
            position = OperatorBlockHistoryPosition(
                anchors, datetime.fromisoformat(timestamp), UUID(blocker), int(version)
            )
            position.validate_pair(pair)
        except ValueError:
            raise InvalidOperatorCursorError from None
        if (
            str(anchors.low_version),
            str(anchors.high_version),
            position.changed_at.isoformat(),
            str(position.blocker_id),
            str(position.version),
        ) != (low_version, high_version, timestamp, blocker, version):
            raise InvalidOperatorCursorError
        return position
