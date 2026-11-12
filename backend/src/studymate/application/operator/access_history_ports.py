"""Bounded account-scoped operator-access history under the existing operator read transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.access_history import (
    MAX_ACCESS_HISTORY_VERSION,
    OperatorAccessHistoryRevision,
)


@dataclass(frozen=True, slots=True)
class OperatorAccessHistoryHead:
    account_id: UUID
    latest_version: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.latest_version, bool)
            or not 0 <= self.latest_version <= MAX_ACCESS_HISTORY_VERSION
        ):
            raise ValueError(
                "Operator-access history head must be an actual bounded nonnegative version"
            )


@dataclass(frozen=True, slots=True)
class OperatorAccessHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_ACCESS_HISTORY_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError(
                "Operator-access history cursor must reference actual bounded source versions"
            )


@dataclass(frozen=True, slots=True)
class OperatorAccessHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorAccessHistoryCursorCodec(Protocol):
    def encode_history(
        self,
        scope: OperatorCursorScope,
        target_id: UUID,
        position: OperatorAccessHistoryPosition,
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str
    ) -> OperatorAccessHistoryPosition: ...


class OperatorAccessHistoryTransaction(OperatorAuditTransaction, Protocol):
    async def access_history_head(self, account_id: UUID) -> OperatorAccessHistoryHead | None:
        """None only for missing AccountRecord; existing empty history has actual head0."""
        ...

    async def access_history_revisions(
        self, account_id: UUID, window: OperatorAccessHistoryWindow
    ) -> tuple[OperatorAccessHistoryRevision, ...]:
        """At most51 revisions/versionDESC with original actor provenance; no current state."""
        ...


class OperatorAccessHistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorAccessHistoryTransaction]: ...
