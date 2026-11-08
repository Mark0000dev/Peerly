"""Bounded metadata, raw revision, and separately paginated removal sources."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.peer_feedback import (
    OperatorFeedbackRemoval,
    OperatorFeedbackRevision,
    OperatorFeedbackRoot,
    require_feedback_version,
)
from studymate.domain.time import require_aware


class OperatorFeedbackDirection(StrEnum):
    GIVEN = "given"
    RECEIVED = "received"


@dataclass(frozen=True, slots=True)
class OperatorFeedbackFilters:
    peer_id: UUID | None = None
    direction: OperatorFeedbackDirection | None = None
    removed: bool | None = None
    changed_from: datetime | None = None
    changed_before: datetime | None = None

    def __post_init__(self) -> None:
        for value in (self.changed_from, self.changed_before):
            if value is not None:
                require_aware(value)
        if (
            self.changed_from is not None
            and self.changed_before is not None
            and self.changed_from >= self.changed_before
        ):
            raise ValueError("Feedback search requires a nonempty half-open changed interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.peer-feedback.v1",
            str(self.peer_id) if self.peer_id is not None else "",
            self.direction.value if self.direction is not None else "",
            "" if self.removed is None else str(self.removed),
            self.changed_from.astimezone(UTC).isoformat() if self.changed_from else "",
            self.changed_before.astimezone(UTC).isoformat() if self.changed_before else "",
        )

    def matches(self, row: OperatorFeedbackRoot, account_id: UUID) -> bool:
        if not row.includes(account_id):
            return False
        peer = row.partner_id if row.reviewer_id == account_id else row.reviewer_id
        return not (
            (self.peer_id is not None and peer != self.peer_id)
            or (self.direction == OperatorFeedbackDirection.GIVEN and row.reviewer_id != account_id)
            or (
                self.direction == OperatorFeedbackDirection.RECEIVED
                and row.partner_id != account_id
            )
            or (self.removed is not None and (row.current_removal_id is not None) != self.removed)
            or (self.changed_from is not None and row.current_changed_at < self.changed_from)
            or (self.changed_before is not None and row.current_changed_at >= self.changed_before)
        )


@dataclass(frozen=True, slots=True)
class OperatorFeedbackTimePosition:
    anchor_at: datetime
    anchor_id: UUID
    before_at: datetime
    before_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_at)
        require_aware(self.before_at)
        if (self.before_at, self.before_id.int) > (self.anchor_at, self.anchor_id.int):
            raise ValueError("Feedback position exceeds its actual source metadata anchor")


@dataclass(frozen=True, slots=True)
class OperatorFeedbackHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        require_feedback_version(self.anchor_version)
        require_feedback_version(self.before_version)
        if self.before_version > self.anchor_version:
            raise ValueError("Feedback history exceeds its actual revision anchor")


@dataclass(frozen=True, slots=True)
class OperatorFeedbackHistoryHead:
    root: OperatorFeedbackRoot
    latest_version: int

    def __post_init__(self) -> None:
        require_feedback_version(self.latest_version)


@dataclass(frozen=True, slots=True)
class OperatorFeedbackHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorFeedbackCursorCodec(Protocol):
    def encode_roots(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorFeedbackTimePosition,
    ) -> str: ...
    def decode_roots(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorFeedbackTimePosition: ...
    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        feedback_id: UUID,
        position: OperatorFeedbackHistoryPosition,
    ) -> str: ...
    def decode_history(
        self, scope: OperatorCursorScope, account_id: UUID, feedback_id: UUID, token: str
    ) -> OperatorFeedbackHistoryPosition: ...
    def encode_removals(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        feedback_id: UUID,
        position: OperatorFeedbackTimePosition,
    ) -> str: ...
    def decode_removals(
        self, scope: OperatorCursorScope, account_id: UUID, feedback_id: UUID, token: str
    ) -> OperatorFeedbackTimePosition: ...


class OperatorFeedbackTransaction(OperatorAuditTransaction, Protocol):
    async def feedback_account(self, account_id: UUID) -> UUID | None: ...
    async def feedback_roots(
        self,
        account_id: UUID,
        filters: OperatorFeedbackFilters,
        position: OperatorFeedbackTimePosition | None,
    ) -> tuple[OperatorFeedbackRoot, ...]: ...
    async def feedback_root(
        self, account_id: UUID, feedback_id: UUID
    ) -> OperatorFeedbackRoot | None: ...
    async def feedback_history_head(
        self, account_id: UUID, feedback_id: UUID
    ) -> OperatorFeedbackHistoryHead | None: ...
    async def feedback_revisions(
        self, account_id: UUID, feedback_id: UUID, window: OperatorFeedbackHistoryWindow
    ) -> tuple[OperatorFeedbackRevision, ...]: ...
    async def feedback_removals(
        self, account_id: UUID, feedback_id: UUID, position: OperatorFeedbackTimePosition | None
    ) -> tuple[OperatorFeedbackRemoval, ...]: ...


class OperatorFeedbackUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorFeedbackTransaction]: ...
