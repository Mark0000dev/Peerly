from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from studymate.application.operator.block_history_ports import OperatorBlockHistoryWindow
from studymate.domain.operator.block_history import (
    OPERATOR_BLOCK_HISTORY_PAGE_SIZE,
    OperatorBlockHistoryAnchors,
    OperatorBlockHistoryHead,
)
from studymate.domain.relationships import AccountPair, BlockRevision
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store

RELATIONSHIP = UUID(int=9200)
PAIR = AccountPair(TARGET, UUID(int=20))


def revision(version: int, blocker_id: UUID = PAIR.low) -> BlockRevision:
    return BlockRevision(RELATIONSHIP, PAIR, blocker_id, version, version % 2 == 1, NOW)


class BlockHistoryStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.accounts = {PAIR.low, PAIR.high}
        self.rows: tuple[BlockRevision, ...] = (revision(1), revision(2), revision(1, PAIR.high))
        self.head_override: OperatorBlockHistoryHead | None = None
        self.rows_override: tuple[BlockRevision, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["BlockHistoryStore"]:
        async with super().transaction():
            yield self

    async def block_history_account(self, account_id: UUID) -> UUID | None:
        self.queried()
        return account_id if account_id in self.accounts else None

    async def block_history_head(
        self, account_id: UUID, relationship_id: UUID
    ) -> OperatorBlockHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        if relationship_id != RELATIONSHIP or account_id not in (PAIR.low, PAIR.high):
            return None
        low = max((row.version for row in self.rows if row.blocker_id == PAIR.low), default=0)
        high = max((row.version for row in self.rows if row.blocker_id == PAIR.high), default=0)
        heads = tuple(
            max(
                (row for row in self.rows if row.blocker_id == blocker), key=lambda row: row.version
            )
            for blocker in (PAIR.high, PAIR.low)
            if any(row.blocker_id == blocker for row in self.rows)
        )
        return OperatorBlockHistoryHead(
            RELATIONSHIP, PAIR, OperatorBlockHistoryAnchors(low, high), heads
        )

    async def block_history_revisions(
        self, head: OperatorBlockHistoryHead, window: OperatorBlockHistoryWindow
    ) -> tuple[BlockRevision, ...]:
        self.queried()
        if self.rows_override is not None:
            return self.rows_override
        previous = (
            (window.before.changed_at, window.before.blocker_id, window.before.version)
            if window.before is not None
            else None
        )
        rows = tuple(
            row
            for row in self.rows
            if row.relationship_id == head.relationship_id
            and row.version <= window.anchors.for_blocker(head.pair, row.blocker_id)
            and (previous is None or (row.changed_at, row.blocker_id, row.version) < previous)
        )
        return tuple(
            sorted(
                rows, key=lambda row: (row.changed_at, row.blocker_id, row.version), reverse=True
            )
        )[: OPERATOR_BLOCK_HISTORY_PAGE_SIZE + 1]
