"""Bounded support metadata reads under the existing operator guard and audit."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.support.cases import SupportReceipt, SupportStatus, SupportTopic
from studymate.domain.support.operator_inbox import OperatorSupportRevision, OperatorSupportSummary
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorSupportFilters:
    case_id: UUID | None = None
    status: SupportStatus | None = None
    topic: SupportTopic | None = None
    actor_id: UUID | None = None
    anonymous: bool | None = None
    received_from: datetime | None = None
    received_before: datetime | None = None

    def __post_init__(self) -> None:
        if self.actor_id is not None and self.anonymous is True:
            raise ValueError("Anonymous support filter cannot specify an account owner")
        for at in (self.received_from, self.received_before):
            if at is not None:
                require_aware(at)
        if (
            self.received_from is not None
            and self.received_before is not None
            and self.received_from >= self.received_before
        ):
            raise ValueError("Support search requires a nonempty half-open time interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.support-search.v1",
            str(self.case_id or ""),
            self.status.value if self.status is not None else "",
            self.topic.value if self.topic is not None else "",
            str(self.actor_id or ""),
            "anonymous"
            if self.anonymous is True
            else "account"
            if self.anonymous is False
            else "all",
            self.received_from.astimezone(UTC).isoformat()
            if self.received_from is not None
            else "",
            self.received_before.astimezone(UTC).isoformat()
            if self.received_before is not None
            else "",
        )


@dataclass(frozen=True, slots=True)
class OperatorSupportPosition:
    anchor_at: datetime
    received_at: datetime
    case_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_at)
        require_aware(self.received_at)
        if self.received_at > self.anchor_at:
            raise ValueError("Support search position exceeds its metadata search anchor")


@dataclass(frozen=True, slots=True)
class OperatorSupportWindow:
    anchor_at: datetime
    before: OperatorSupportPosition | None


@dataclass(frozen=True, slots=True)
class OperatorSupportHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.anchor_version, bool)
            or isinstance(self.before_version, bool)
            or self.anchor_version < 1
            or not 1 <= self.before_version <= self.anchor_version
        ):
            raise ValueError("Support history cursor requires actual bounded positive versions")


@dataclass(frozen=True, slots=True)
class OperatorSupportHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorSupportInboxCursorCodec(Protocol):
    def encode_inbox(
        self, scope: OperatorCursorScope, fingerprint: bytes, position: OperatorSupportPosition
    ) -> str: ...

    def decode_inbox(
        self, scope: OperatorCursorScope, fingerprint: bytes, token: str, now: datetime
    ) -> OperatorSupportPosition: ...

    def encode_history(
        self, scope: OperatorCursorScope, case_id: UUID, position: OperatorSupportHistoryPosition
    ) -> str: ...

    def decode_history(
        self, scope: OperatorCursorScope, case_id: UUID, token: str
    ) -> OperatorSupportHistoryPosition: ...


class OperatorSupportInboxTransaction(OperatorAuditTransaction, Protocol):
    async def search_support_cases(
        self, filters: OperatorSupportFilters, window: OperatorSupportWindow
    ) -> tuple[OperatorSupportSummary, ...]:
        """At most50+lookahead, current actual status; no content/address search or projection."""
        ...

    async def support_history_head(self, case_id: UUID) -> SupportReceipt | None: ...

    async def support_history(
        self, case_id: UUID, window: OperatorSupportHistoryWindow
    ) -> tuple[OperatorSupportRevision, ...]:
        """At most50+lookahead, original retained revisions and actual operator grant refs."""
        ...


class OperatorSupportInboxUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorSupportInboxTransaction]: ...
