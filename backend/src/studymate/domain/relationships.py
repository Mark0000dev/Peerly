"""Canonical account pairs and directional block history; no implicit connection."""

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class AccountPair:
    low: UUID
    high: UUID

    def __post_init__(self) -> None:
        if self.low.int >= self.high.int:
            raise ValueError("A relationship needs two distinct, canonically ordered accounts")

    @classmethod
    def between(cls, first: UUID, second: UUID) -> "AccountPair":
        return cls(first, second) if first.int < second.int else cls(second, first)

    def counterpart(self, account_id: UUID) -> UUID:
        if account_id == self.low:
            return self.high
        if account_id == self.high:
            return self.low
        raise ValueError("Account is not a participant of this pair")


@dataclass(frozen=True, slots=True)
class BlockRevision:
    relationship_id: UUID
    pair: AccountPair
    blocker_id: UUID
    version: int
    blocked: bool
    changed_at: datetime

    def __post_init__(self) -> None:
        self.pair.counterpart(self.blocker_id)
        require_aware(self.changed_at)
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Block revision must be a positive integer")

    @property
    def target_id(self) -> UUID:
        return self.pair.counterpart(self.blocker_id)

    def change(self, *, actor_id: UUID, blocked: bool, at: datetime) -> "BlockRevision":
        require_aware(at)
        if actor_id != self.blocker_id:
            raise ValueError("Only the blocker may change their directional block")
        if at < self.changed_at:
            raise ValueError("Block action cannot precede its saved revision")
        if blocked == self.blocked:
            return self
        return replace(self, version=self.version + 1, blocked=blocked, changed_at=at)


def pair_is_blocked(first: BlockRevision | None, second: BlockRevision | None) -> bool:
    if (
        first is not None
        and second is not None
        and (
            first.relationship_id != second.relationship_id
            or first.pair != second.pair
            or first.blocker_id == second.blocker_id
        )
    ):
        raise ValueError("Block projections must describe opposite sides of the same pair")
    return (first is not None and first.blocked) or (second is not None and second.blocked)
