"""Explicit retained goal root/history ports under the actual operator audit transaction."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.goals import (
    MAX_OPERATOR_GOAL_VERSION,
    OperatorGoalRevision,
    OperatorGoalRoot,
)
from studymate.domain.time import require_aware


class OperatorGoalState(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class OperatorGoalFilters:
    state: OperatorGoalState | None = None
    created_from: datetime | None = None
    created_before: datetime | None = None

    def __post_init__(self) -> None:
        for value in (self.created_from, self.created_before):
            if value is not None:
                require_aware(value)
        if (
            self.created_from is not None
            and self.created_before is not None
            and self.created_from >= self.created_before
        ):
            raise ValueError("Goal root search needs a nonempty half-open time interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.goal-roots.v1",
            self.state.value if self.state is not None else "",
            self.created_from.astimezone(UTC).isoformat() if self.created_from is not None else "",
            self.created_before.astimezone(UTC).isoformat()
            if self.created_before is not None
            else "",
        )

    def matches(self, goal: OperatorGoalRoot) -> bool:
        return not (
            (self.state == OperatorGoalState.ACTIVE and goal.completed_at is not None)
            or (self.state == OperatorGoalState.COMPLETED and goal.completed_at is None)
            or (self.created_from is not None and goal.created_at < self.created_from)
            or (self.created_before is not None and goal.created_at >= self.created_before)
        )


@dataclass(frozen=True, slots=True)
class OperatorGoalRootPosition:
    anchor_created_at: datetime
    anchor_goal_id: UUID
    before_created_at: datetime
    before_goal_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_created_at)
        require_aware(self.before_created_at)
        if (self.before_created_at, self.before_goal_id.int) > (
            self.anchor_created_at,
            self.anchor_goal_id.int,
        ):
            raise ValueError("Goal root position exceeds its actual metadata anchor")


@dataclass(frozen=True, slots=True)
class OperatorGoalHistoryHead:
    goal: OperatorGoalRoot
    latest_version: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.latest_version, bool)
            or not 1 <= self.latest_version <= MAX_OPERATOR_GOAL_VERSION
        ):
            raise ValueError("Goal history head requires an actual positive source version")


@dataclass(frozen=True, slots=True)
class OperatorGoalHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_OPERATOR_GOAL_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError("Goal history position exceeds its actual version anchor")


@dataclass(frozen=True, slots=True)
class OperatorGoalHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorGoalCursorCodec(Protocol):
    def encode_roots(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorGoalRootPosition,
    ) -> str: ...

    def decode_roots(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorGoalRootPosition: ...

    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        goal_id: UUID,
        position: OperatorGoalHistoryPosition,
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, account_id: UUID, goal_id: UUID, token: str
    ) -> OperatorGoalHistoryPosition: ...


class OperatorGoalTransaction(OperatorAuditTransaction, Protocol):
    async def goal_account(self, account_id: UUID) -> UUID | None:
        """Actual AccountRecord existence without student/target lifecycle filtering."""
        ...

    async def goal_roots(
        self,
        account_id: UUID,
        filters: OperatorGoalFilters,
        position: OperatorGoalRootPosition | None,
    ) -> tuple[OperatorGoalRoot, ...]:
        """At most51, created_at/idDESC; current metadata, NOT a replay/commit watermark."""
        ...

    async def goal_history_head(
        self, account_id: UUID, goal_id: UUID
    ) -> OperatorGoalHistoryHead | None:
        """Exact owned root plus max ALL stored revisions, not its current pointer."""
        ...

    async def goal_history_revisions(
        self, account_id: UUID, goal_id: UUID, window: OperatorGoalHistoryWindow
    ) -> tuple[OperatorGoalRevision, ...]:
        """At most51 exact raw owned revisions/versionDESC; no current catalogue reconstruction."""
        ...


class OperatorGoalUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorGoalTransaction]: ...
