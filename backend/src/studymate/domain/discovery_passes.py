"""Retained private decisions; Undo ends at the next committed deck decision."""

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from studymate.domain.discovery_context import DiscoveryContext
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class PrivatePassRevision:
    id: UUID
    context: DiscoveryContext
    target_id: UUID
    version: int
    passed: bool
    decision_sequence: int
    changed_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.changed_at)
        if self.context.account_id == self.target_id:
            raise ValueError("A private pass cannot target its owner")
        for value in (self.version, self.decision_sequence):
            if isinstance(value, bool) or value < 1:
                raise ValueError("Private decision versions and sequences must be positive")

    def can_undo(self, latest_sequence: int) -> bool:
        return self.passed and self.decision_sequence == latest_sequence

    def reconsider(self, sequence: int, at: datetime) -> "PrivatePassRevision":
        return self._change(False, sequence, at)

    def pass_again(self, sequence: int, at: datetime) -> "PrivatePassRevision":
        return self._change(True, sequence, at)

    def _change(self, passed: bool, sequence: int, at: datetime) -> "PrivatePassRevision":
        require_aware(at)
        if at < self.changed_at:
            raise ValueError("A private decision cannot precede its current revision")
        if passed == self.passed:
            return self
        if isinstance(sequence, bool) or sequence <= self.decision_sequence:
            raise ValueError("A new decision needs a later committed sequence")
        return replace(
            self,
            version=self.version + 1,
            passed=passed,
            decision_sequence=sequence,
            changed_at=at,
        )
