"""Bounded account-scoped help history under the existing operator read transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.help_history import (
    MAX_HELP_HISTORY_VERSION,
    OperatorHelpHistoryRevision,
)


@dataclass(frozen=True, slots=True)
class OperatorHelpHistoryHead:
    account_id: UUID
    latest_version: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.latest_version, bool)
            or not 0 <= self.latest_version <= MAX_HELP_HISTORY_VERSION
        ):
            raise ValueError("Help history head must be an actual bounded nonnegative version")


@dataclass(frozen=True, slots=True)
class OperatorHelpHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_HELP_HISTORY_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError("Help history cursor must reference actual bounded source versions")


@dataclass(frozen=True, slots=True)
class OperatorHelpHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorHelpHistoryCursorCodec(Protocol):
    def encode_history(
        self, scope: OperatorCursorScope, target_id: UUID, position: OperatorHelpHistoryPosition
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str
    ) -> OperatorHelpHistoryPosition: ...


class OperatorHelpHistoryTransaction(OperatorAuditTransaction, Protocol):
    async def help_history_head(self, account_id: UUID) -> OperatorHelpHistoryHead | None:
        """None only for missing AccountRecord; existing empty history has actual head0."""
        ...

    async def help_history_revisions(
        self, account_id: UUID, window: OperatorHelpHistoryWindow
    ) -> tuple[OperatorHelpHistoryRevision, ...]:
        """At most51 revisions/versionDESC and selections by stored slot; no current state."""
        ...


class OperatorHelpHistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorHelpHistoryTransaction]: ...
