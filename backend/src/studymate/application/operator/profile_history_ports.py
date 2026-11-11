"""Bounded account-scoped profile history under the existing operator read transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.profile_history import (
    MAX_PROFILE_HISTORY_VERSION,
    OperatorProfileHistoryRevision,
)


@dataclass(frozen=True, slots=True)
class OperatorProfileHistoryHead:
    account_id: UUID
    latest_version: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.latest_version, bool)
            or not 0 <= self.latest_version <= MAX_PROFILE_HISTORY_VERSION
        ):
            raise ValueError("Profile history head must be an actual bounded nonnegative version")


@dataclass(frozen=True, slots=True)
class OperatorProfileHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_PROFILE_HISTORY_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError("Profile history cursor must reference actual bounded source versions")


@dataclass(frozen=True, slots=True)
class OperatorProfileHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorProfileHistoryCursorCodec(Protocol):
    def encode_history(
        self, scope: OperatorCursorScope, target_id: UUID, position: OperatorProfileHistoryPosition
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str
    ) -> OperatorProfileHistoryPosition: ...


class OperatorProfileHistoryTransaction(OperatorAuditTransaction, Protocol):
    async def profile_history_head(self, account_id: UUID) -> OperatorProfileHistoryHead | None:
        """None only for missing AccountRecord; existing empty history has actual head0."""
        ...

    async def profile_history_revisions(
        self, account_id: UUID, window: OperatorProfileHistoryWindow
    ) -> tuple[OperatorProfileHistoryRevision, ...]:
        """At most51 revisions/versionDESC and languages by stored slot; no current state."""
        ...


class OperatorProfileHistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorProfileHistoryTransaction]: ...
