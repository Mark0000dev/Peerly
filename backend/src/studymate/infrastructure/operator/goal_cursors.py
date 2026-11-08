"""Distinct goal root/filter and owned revision cursor purposes; never role authority."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.goal_ports import (
    OperatorGoalHistoryPosition,
    OperatorGoalRootPosition,
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
class FernetOperatorGoalCursorCodec:
    roots: Fernet = field(repr=False)
    history: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, envelope_key: bytes) -> "FernetOperatorGoalCursorCodec":
        if len(envelope_key) != KEY_BYTES:
            raise ValueError("Goal inspection needs the configured32-byte envelope key")
        return cls(
            Fernet(cursor_key(envelope_key, b"peerly.operator.goal-roots.v1")),
            Fernet(cursor_key(envelope_key, b"peerly.operator.goal-history.v1")),
        )

    def encode_roots(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorGoalRootPosition,
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Goal roots require the actual query HMAC")
        return encode_cursor(
            self.roots,
            (
                "operator-goal-roots-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                fingerprint.hex(),
                position.anchor_created_at.isoformat(),
                str(position.anchor_goal_id),
                position.before_created_at.isoformat(),
                str(position.before_goal_id),
            ),
        )

    def decode_roots(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorGoalRootPosition:
        version, actor, grant, account, digest, anchor_at, anchor_goal, before_at, before_goal = (
            cursor_payload(self.roots, token, ROOT_CURSOR_PARTS)
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, account, digest) != (
            "operator-goal-roots-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            return OperatorGoalRootPosition(
                datetime.fromisoformat(anchor_at),
                UUID(anchor_goal),
                datetime.fromisoformat(before_at),
                UUID(before_goal),
            )
        except ValueError:
            raise InvalidOperatorCursorError from None

    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        goal_id: UUID,
        position: OperatorGoalHistoryPosition,
    ) -> str:
        return encode_cursor(
            self.history,
            (
                "operator-goal-history-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                str(goal_id),
                str(position.anchor_version),
                str(position.before_version),
            ),
        )

    def decode_history(
        self, scope: OperatorCursorScope, account_id: UUID, goal_id: UUID, token: str
    ) -> OperatorGoalHistoryPosition:
        version, actor, grant, account, goal, anchor, before = cursor_payload(
            self.history, token, HISTORY_CURSOR_PARTS
        )
        if (version, actor, grant, account, goal) != (
            "operator-goal-history-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            str(goal_id),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorGoalHistoryPosition(int(anchor), int(before))
        except ValueError:
            raise InvalidOperatorCursorError from None
        if (str(position.anchor_version), str(position.before_version)) != (anchor, before):
            raise InvalidOperatorCursorError
        return position
