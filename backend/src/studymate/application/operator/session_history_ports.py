"""Issuance-bounded keyset pagination; mutable revocation state is read afresh."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.session_history import SessionHistoryEntry
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class SessionHistoryPosition:
    as_of: datetime
    issued_at: datetime
    session_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.as_of)
        require_aware(self.issued_at)
        if self.issued_at > self.as_of:
            raise ValueError("History position must precede its issuance boundary")


@dataclass(frozen=True, slots=True)
class SessionHistoryWindow:
    as_of: datetime
    before: SessionHistoryPosition | None


class SessionHistoryCursorCodec(Protocol):
    def encode_history(
        self, scope: OperatorCursorScope, target_id: UUID, position: SessionHistoryPosition
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str, now: datetime
    ) -> SessionHistoryPosition: ...


class SessionHistoryTransaction(OperatorAuditTransaction, Protocol):
    async def session_history_account_exists(self, account_id: UUID) -> bool: ...

    async def session_history_sessions(
        self, account_id: UUID, window: SessionHistoryWindow
    ) -> tuple[SessionHistoryEntry, ...]: ...


class SessionHistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[SessionHistoryTransaction]: ...
