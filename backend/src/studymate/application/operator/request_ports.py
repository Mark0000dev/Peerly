"""Explicit account-participant raw request sources, no Requests mutation/ACK workflow."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.operator.connection_requests import (
    MAX_OPERATOR_REQUEST_VERSION,
    OperatorRequestAcknowledgement,
    OperatorRequestRevision,
    OperatorRequestRoot,
    OperatorRequestSnapshot,
)
from studymate.domain.requests.states import RequestState
from studymate.domain.time import require_aware


class OperatorRequestDirection(StrEnum):
    SENT = "sent"
    RECEIVED = "received"


@dataclass(frozen=True, slots=True)
class OperatorRequestFilters:
    peer_id: UUID | None = None
    direction: OperatorRequestDirection | None = None
    mode: DiscoveryMode | None = None
    state: RequestState | None = None
    sent_from: datetime | None = None
    sent_before: datetime | None = None

    def __post_init__(self) -> None:
        for value in (self.sent_from, self.sent_before):
            if value is not None:
                require_aware(value)
        if (
            self.sent_from is not None
            and self.sent_before is not None
            and self.sent_from >= self.sent_before
        ):
            raise ValueError("Request inspection requires a nonempty half-open sent interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.connection-requests.v1",
            str(self.peer_id) if self.peer_id is not None else "",
            self.direction.value if self.direction is not None else "",
            self.mode.value if self.mode is not None else "",
            self.state.value if self.state is not None else "",
            self.sent_from.astimezone(UTC).isoformat() if self.sent_from is not None else "",
            self.sent_before.astimezone(UTC).isoformat() if self.sent_before is not None else "",
        )

    def matches(self, row: OperatorRequestRoot, account_id: UUID) -> bool:
        if not row.includes(account_id):
            return False
        peer_id = row.recipient_id if row.sender_id == account_id else row.sender_id
        return not (
            (self.peer_id is not None and peer_id != self.peer_id)
            or (self.direction == OperatorRequestDirection.SENT and row.sender_id != account_id)
            or (
                self.direction == OperatorRequestDirection.RECEIVED
                and row.recipient_id != account_id
            )
            or (self.mode is not None and row.mode != self.mode)
            or (self.state is not None and row.state != self.state)
            or (self.sent_from is not None and row.sent_at < self.sent_from)
            or (self.sent_before is not None and row.sent_at >= self.sent_before)
        )


@dataclass(frozen=True, slots=True)
class OperatorRequestPosition:
    anchor_sent_at: datetime
    anchor_request_id: UUID
    before_sent_at: datetime
    before_request_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_sent_at)
        require_aware(self.before_sent_at)
        if (self.before_sent_at, self.before_request_id.int) > (
            self.anchor_sent_at,
            self.anchor_request_id.int,
        ):
            raise ValueError("Request inspection exceeds its actual sent metadata anchor")


@dataclass(frozen=True, slots=True)
class OperatorRequestHistoryHead:
    snapshot: OperatorRequestSnapshot
    latest_version: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.latest_version, bool)
            or not 1 <= self.latest_version <= MAX_OPERATOR_REQUEST_VERSION
        ):
            raise ValueError("Request history requires the actual positive source head")


@dataclass(frozen=True, slots=True)
class OperatorRequestHistoryPosition:
    anchor_version: int
    before_version: int

    def __post_init__(self) -> None:
        if (
            any(
                isinstance(value, bool) or not 1 <= value <= MAX_OPERATOR_REQUEST_VERSION
                for value in (self.anchor_version, self.before_version)
            )
            or self.before_version > self.anchor_version
        ):
            raise ValueError("Request history position exceeds its actual version anchor")


@dataclass(frozen=True, slots=True)
class OperatorRequestHistoryWindow:
    anchor_version: int
    before_version: int | None


class OperatorRequestCursorCodec(Protocol):
    def encode_roots(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorRequestPosition,
    ) -> str: ...
    def decode_roots(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorRequestPosition: ...
    def encode_history(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        request_id: UUID,
        position: OperatorRequestHistoryPosition,
    ) -> str: ...
    def decode_history(
        self, scope: OperatorCursorScope, account_id: UUID, request_id: UUID, token: str
    ) -> OperatorRequestHistoryPosition: ...


class OperatorRequestTransaction(OperatorAuditTransaction, Protocol):
    async def request_account(self, account_id: UUID) -> UUID | None: ...
    async def request_roots(
        self,
        account_id: UUID,
        filters: OperatorRequestFilters,
        position: OperatorRequestPosition | None,
    ) -> tuple[OperatorRequestRoot, ...]: ...
    async def request_history_head(
        self, account_id: UUID, request_id: UUID
    ) -> OperatorRequestHistoryHead | None: ...
    async def request_revisions(
        self, account_id: UUID, request_id: UUID, window: OperatorRequestHistoryWindow
    ) -> tuple[OperatorRequestRevision, ...]: ...
    async def request_page_acknowledgements(
        self, account_id: UUID, request_id: UUID, versions: tuple[int, ...]
    ) -> tuple[OperatorRequestAcknowledgement, ...]:
        """Only actual ACKs for visible revisions +their linked disclosures, at most2/version."""
        ...


class OperatorRequestUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorRequestTransaction]: ...
