"""Actual directional block sources; a relationship is not proof of an accepted chat."""

from dataclasses import dataclass
from uuid import UUID

from studymate.domain.relationships import AccountPair, BlockRevision

OPERATOR_BLOCK_HISTORY_PAGE_SIZE = 50
MAX_BLOCK_HISTORY_VERSION = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class OperatorBlockHistoryAnchors:
    low_version: int
    high_version: int

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool) or not 0 <= value <= MAX_BLOCK_HISTORY_VERSION
            for value in (self.low_version, self.high_version)
        ):
            raise ValueError("Block history anchors require actual bounded directional versions")

    def for_blocker(self, pair: AccountPair, blocker: UUID) -> int:
        pair.counterpart(blocker)
        return self.low_version if blocker == pair.low else self.high_version


@dataclass(frozen=True, slots=True)
class OperatorBlockHistoryHead:
    relationship_id: UUID
    pair: AccountPair
    anchors: OperatorBlockHistoryAnchors
    current_heads: tuple[BlockRevision, ...]

    def __post_init__(self) -> None:
        blockers = set()
        for source in self.current_heads:
            if (
                source.relationship_id != self.relationship_id
                or source.pair != self.pair
                or source.blocker_id in blockers
                or source.version > self.anchors.for_blocker(self.pair, source.blocker_id)
            ):
                raise ValueError("Block history head differs from actual directional source proof")
            blockers.add(source.blocker_id)
