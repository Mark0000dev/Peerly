"""Creation-bounded keyset pagination; mutable delivery state is read afresh."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.email_history import EmailHistoryChallenge
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class EmailHistoryPosition:
    as_of: datetime
    created_at: datetime
    challenge_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.as_of)
        require_aware(self.created_at)
        if self.created_at > self.as_of:
            raise ValueError("History position must precede its creation boundary")


@dataclass(frozen=True, slots=True)
class EmailHistoryWindow:
    as_of: datetime
    before: EmailHistoryPosition | None


class EmailHistoryCursorCodec(Protocol):
    def encode_history(
        self, scope: OperatorCursorScope, target_id: UUID, position: EmailHistoryPosition
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, target_id: UUID, token: str, now: datetime
    ) -> EmailHistoryPosition: ...


class EmailHistoryTransaction(OperatorAuditTransaction, Protocol):
    async def email_history_account_exists(self, account_id: UUID) -> bool: ...

    async def email_history_challenges(
        self, account_id: UUID, window: EmailHistoryWindow
    ) -> tuple[EmailHistoryChallenge, ...]: ...


class EmailHistoryUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[EmailHistoryTransaction]: ...
