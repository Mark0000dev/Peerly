"""Bounded account-scoped preference history under the existing operator read transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.preference_history import (
    MAX_PREFERENCE_HISTORY_VERSION,
    OperatorPreferenceHistoryRevision,
)


@dataclass(frozen=True, slots=True)
class OperatorPreferenceHistoryHead:
    account_id: UUID
    latest_version: int
    current: OperatorPreferenceHistoryRevision | None = None

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
            or not 0 <= self.latest_version <= MAX_PREFERENCE_HISTORY_VERSION
        ):
            raise ValueError(
                "Preference history head must be an actual bounded nonnegative version"
            )


@dataclass(frozen=True, slots=True)
class OperatorPreferenceHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_PREFERENCE_HISTORY_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError(
                "Preference history cursor must reference actual bounded source versions"
            )


@dataclass(frozen=True, slots=True)
class OperatorPreferenceHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorPreferenceHistoryCursorCodec(Protocol):
    def encode_history(
        self,
        scope: OperatorCursorScope,
        target_id: UUID,
        position: OperatorPreferenceHistoryPosition,
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str
    ) -> OperatorPreferenceHistoryPosition: ...


class OperatorPreferenceHistoryTransaction(OperatorAuditTransaction, Protocol):
    async def preference_history_head(
        self, account_id: UUID
    ) -> OperatorPreferenceHistoryHead | None:
        """None only for missing AccountRecord; existing empty history has actual head0."""
        ...

    async def preference_history_revisions(
        self, account_id: UUID, window: OperatorPreferenceHistoryWindow
    ) -> tuple[OperatorPreferenceHistoryRevision, ...]:
        """At most51 actual stored choices/versionDESC; no implicit default or transport state."""
        ...


class OperatorPreferenceHistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorPreferenceHistoryTransaction]: ...
