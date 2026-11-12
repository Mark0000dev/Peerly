"""Bounded account-scoped visibility history under the existing operator read transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.visibility_history import (
    MAX_VISIBILITY_HISTORY_VERSION,
    OperatorVisibilityHistoryRevision,
)


@dataclass(frozen=True, slots=True)
class OperatorVisibilityHistoryHead:
    account_id: UUID
    latest_version: int
    current: OperatorVisibilityHistoryRevision | None = None

    def __post_init__(self) -> None:
        if (
            (
                self.current is not None
                and (
                    self.current.account_id != self.account_id
                    or self.current.version != self.latest_version
                )
            )
            or (self.current is None and self.latest_version != 0)
            or isinstance(self.latest_version, bool)
            or not 0 <= self.latest_version <= MAX_VISIBILITY_HISTORY_VERSION
        ):
            raise ValueError(
                "Visibility history head must be an actual bounded nonnegative version"
            )


@dataclass(frozen=True, slots=True)
class OperatorVisibilityHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_VISIBILITY_HISTORY_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError(
                "Visibility history cursor must reference actual bounded source versions"
            )


@dataclass(frozen=True, slots=True)
class OperatorVisibilityHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorVisibilityHistoryCursorCodec(Protocol):
    def encode_history(
        self,
        scope: OperatorCursorScope,
        target_id: UUID,
        position: OperatorVisibilityHistoryPosition,
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str
    ) -> OperatorVisibilityHistoryPosition: ...


class OperatorVisibilityHistoryTransaction(OperatorAuditTransaction, Protocol):
    async def visibility_history_head(
        self, account_id: UUID
    ) -> OperatorVisibilityHistoryHead | None:
        """None only for missing AccountRecord; existing empty history has actual head0."""
        ...

    async def visibility_history_revisions(
        self, account_id: UUID, window: OperatorVisibilityHistoryWindow
    ) -> tuple[OperatorVisibilityHistoryRevision, ...]:
        """At most51 stored visibility sources/versionDESC.

        No inferred event, origin or effective exposure.
        """
        ...


class OperatorVisibilityHistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorVisibilityHistoryTransaction]: ...
