"""Bounded account-scoped lifecycle history under the existing operator read transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.lifecycle_history import (
    MAX_LIFECYCLE_HISTORY_VERSION,
    OperatorLifecycleHistoryRevision,
)


@dataclass(frozen=True, slots=True)
class OperatorLifecycleHistoryHead:
    account_id: UUID
    latest_version: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.latest_version, bool)
            or not 0 <= self.latest_version <= MAX_LIFECYCLE_HISTORY_VERSION
        ):
            raise ValueError("Lifecycle history head must be an actual bounded nonnegative version")


@dataclass(frozen=True, slots=True)
class OperatorLifecycleHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_LIFECYCLE_HISTORY_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError(
                "Lifecycle history cursor must reference actual bounded source versions"
            )


@dataclass(frozen=True, slots=True)
class OperatorLifecycleHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorLifecycleHistoryCursorCodec(Protocol):
    def encode_history(
        self,
        scope: OperatorCursorScope,
        target_id: UUID,
        position: OperatorLifecycleHistoryPosition,
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str
    ) -> OperatorLifecycleHistoryPosition: ...


class OperatorLifecycleHistoryTransaction(OperatorAuditTransaction, Protocol):
    async def lifecycle_history_head(self, account_id: UUID) -> OperatorLifecycleHistoryHead | None:
        """None only for missing AccountRecord; existing empty history has actual head0."""
        ...

    async def lifecycle_history_revisions(
        self, account_id: UUID, window: OperatorLifecycleHistoryWindow
    ) -> tuple[OperatorLifecycleHistoryRevision, ...]:
        """At most51 revisions/versionDESC with original actor provenance; no current state."""
        ...


class OperatorLifecycleHistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorLifecycleHistoryTransaction]: ...
