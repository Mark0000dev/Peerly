"""Three independent retained feedback pagination purposes, never operator authority."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.feedback_ports import (
    OperatorFeedbackHistoryPosition,
    OperatorFeedbackTimePosition,
)
from studymate.infrastructure.operator.cursors import (
    KEY_BYTES,
    cursor_key,
    cursor_payload,
    encode_cursor,
)

ROOT_PARTS = 9
HISTORY_PARTS = 7
REMOVAL_PARTS = 9


@dataclass(frozen=True, slots=True)
class FernetOperatorFeedbackCursorCodec:
    roots: Fernet = field(repr=False)
    history: Fernet = field(repr=False)
    removals: Fernet = field(repr=False)

    @classmethod
    def from_key(cls, key: bytes) -> "FernetOperatorFeedbackCursorCodec":
        if len(key) != KEY_BYTES:
            raise ValueError("Feedback inspection needs the configured32-byte envelope key")
        return cls(
            Fernet(cursor_key(key, b"peerly.operator.peer-feedback.v1")),
            Fernet(cursor_key(key, b"peerly.operator.peer-feedback-history.v1")),
            Fernet(cursor_key(key, b"peerly.operator.peer-feedback-removals.v1")),
        )

    def encode_roots(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorFeedbackTimePosition,
    ) -> str:
        if len(fingerprint) != KEY_BYTES:
            raise ValueError("Feedback root cursor requires its query HMAC")
        return encode_cursor(
            self.roots,
            (
                "operator-feedback-roots-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                fingerprint.hex(),
                position.anchor_at.isoformat(),
                str(position.anchor_id),
                position.before_at.isoformat(),
                str(position.before_id),
            ),
        )

    def decode_roots(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorFeedbackTimePosition:
        version, actor, grant, account, digest, anchor_at, anchor, before_at, before = (
            cursor_payload(self.roots, token, ROOT_PARTS)
        )
        if len(fingerprint) != KEY_BYTES or (version, actor, grant, account, digest) != (
            "operator-feedback-roots-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            fingerprint.hex(),
        ):
            raise InvalidOperatorCursorError
        try:
            return OperatorFeedbackTimePosition(
                datetime.fromisoformat(anchor_at),
                UUID(anchor),
                datetime.fromisoformat(before_at),
                UUID(before),
            )
        except ValueError:
            raise InvalidOperatorCursorError from None

    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        feedback_id: UUID,
        position: OperatorFeedbackHistoryPosition,
    ) -> str:
        return encode_cursor(
            self.history,
            (
                "operator-feedback-history-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                str(feedback_id),
                str(position.anchor_version),
                str(position.before_version),
            ),
        )

    def decode_history(
        self, scope: OperatorCursorScope, account_id: UUID, feedback_id: UUID, token: str
    ) -> OperatorFeedbackHistoryPosition:
        version, actor, grant, account, feedback, anchor, before = cursor_payload(
            self.history, token, HISTORY_PARTS
        )
        if (version, actor, grant, account, feedback) != (
            "operator-feedback-history-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            str(feedback_id),
        ):
            raise InvalidOperatorCursorError
        try:
            position = OperatorFeedbackHistoryPosition(int(anchor), int(before))
        except ValueError:
            raise InvalidOperatorCursorError from None
        if (str(position.anchor_version), str(position.before_version)) != (anchor, before):
            raise InvalidOperatorCursorError
        return position

    def encode_removals(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        feedback_id: UUID,
        position: OperatorFeedbackTimePosition,
    ) -> str:
        return encode_cursor(
            self.removals,
            (
                "operator-feedback-removals-v1",
                str(scope.account_id),
                str(scope.access_version),
                str(account_id),
                str(feedback_id),
                position.anchor_at.isoformat(),
                str(position.anchor_id),
                position.before_at.isoformat(),
                str(position.before_id),
            ),
        )

    def decode_removals(
        self, scope: OperatorCursorScope, account_id: UUID, feedback_id: UUID, token: str
    ) -> OperatorFeedbackTimePosition:
        version, actor, grant, account, feedback, anchor_at, anchor, before_at, before = (
            cursor_payload(self.removals, token, REMOVAL_PARTS)
        )
        if (version, actor, grant, account, feedback) != (
            "operator-feedback-removals-v1",
            str(scope.account_id),
            str(scope.access_version),
            str(account_id),
            str(feedback_id),
        ):
            raise InvalidOperatorCursorError
        try:
            return OperatorFeedbackTimePosition(
                datetime.fromisoformat(anchor_at),
                UUID(anchor),
                datetime.fromisoformat(before_at),
                UUID(before),
            )
        except ValueError:
            raise InvalidOperatorCursorError from None
