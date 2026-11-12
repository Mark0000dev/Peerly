from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.block_history import (
    MAX_BLOCK_HISTORY_VERSION,
    OperatorBlockHistoryAnchors,
    OperatorBlockHistoryHead,
)
from studymate.domain.relationships import AccountPair, BlockRevision
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorBlockHistoryPosition:
    anchors: OperatorBlockHistoryAnchors
    changed_at: datetime
    blocker_id: UUID
    version: int

    def __post_init__(self) -> None:
        require_aware(self.changed_at)
        if isinstance(self.version, bool) or not 1 <= self.version <= MAX_BLOCK_HISTORY_VERSION:
            raise ValueError("Block history position requires an actual bounded positive version")

    def validate_pair(self, pair: AccountPair) -> None:
        if self.version > self.anchors.for_blocker(pair, self.blocker_id):
            raise ValueError("Block history position exceeds its actual directional source anchor")


@dataclass(frozen=True, slots=True)
class OperatorBlockHistoryWindow:
    anchors: OperatorBlockHistoryAnchors
    before: OperatorBlockHistoryPosition | None


class OperatorBlockHistoryCursorCodec(Protocol):
    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        relationship_id: UUID,
        pair: AccountPair,
        position: OperatorBlockHistoryPosition,
    ) -> str: ...
    def decode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        relationship_id: UUID,
        pair: AccountPair,
        token: str,
    ) -> OperatorBlockHistoryPosition: ...


class OperatorBlockHistoryTransaction(OperatorAuditTransaction, Protocol):
    async def block_history_account(self, account_id: UUID) -> UUID | None: ...
    async def block_history_head(
        self, account_id: UUID, relationship_id: UUID
    ) -> OperatorBlockHistoryHead | None: ...
    async def block_history_revisions(
        self, head: OperatorBlockHistoryHead, window: OperatorBlockHistoryWindow
    ) -> tuple[BlockRevision, ...]: ...


class OperatorBlockHistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorBlockHistoryTransaction]: ...
