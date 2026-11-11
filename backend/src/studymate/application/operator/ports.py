from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.identity.sessions import IdentityReader
from studymate.application.operator.data import OperatorAccountDetail, OperatorAccountSummary
from studymate.application.operator.filters import OperatorAccountFilters
from studymate.domain.messaging import ChatConversation, ConfirmedMessage
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorAccountPosition:
    as_of: datetime
    created_at: datetime
    account_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.as_of)
        require_aware(self.created_at)
        if self.created_at > self.as_of:
            raise ValueError("Account position exceeds its fixed query anchor")


@dataclass(frozen=True, slots=True)
class OperatorAccountWindow:
    as_of: datetime
    before: OperatorAccountPosition | None


@dataclass(frozen=True, slots=True)
class OperatorMessagePosition:
    anchor_sequence: int
    before_sequence: int

    def __post_init__(self) -> None:
        limit = (1 << 63) - 1
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= limit
                for value in (self.anchor_sequence, self.before_sequence)
            )
            or self.before_sequence > self.anchor_sequence
        ):
            raise ValueError("Inspection cursor requires committed bounded message sequences")


@dataclass(frozen=True, slots=True)
class OperatorMessageWindow:
    anchor_sequence: int
    before_sequence: int | None


class OperatorAuditTransaction(IdentityReader, Protocol):
    async def operator_access(self, account_id: UUID) -> OperatorAccess | None:
        """Explicit current Google-linked DB grant; lock account/session before role root."""
        ...

    async def save_operator_audit(self, audit: OperatorAudit) -> None:
        """Durable metadata-only source in the SAME read transaction before data return."""
        ...


class OperatorAccountTransaction(OperatorAuditTransaction, Protocol):
    async def search_operator_accounts(
        self, filters: OperatorAccountFilters, window: OperatorAccountWindow
    ) -> tuple[OperatorAccountSummary, ...]:
        """At most21, created_at/id DESC, actual source joins/no student lifecycle filter."""
        ...

    async def operator_account(self, account_id: UUID) -> OperatorAccountDetail | None: ...


class OperatorAccountUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorAccountTransaction]: ...


class OperatorMessageTransaction(OperatorAuditTransaction, Protocol):
    async def operator_conversation(self, conversation_id: UUID) -> ChatConversation | None:
        """Actual retained conversation; explicit operator role, never participant gate."""
        ...

    async def operator_messages(
        self, conversation_id: UUID, window: OperatorMessageWindow
    ) -> tuple[ConfirmedMessage, ...]:
        """At most51, descending server sequence, no payload search or N+1."""
        ...


class OperatorMessageUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorMessageTransaction]: ...
