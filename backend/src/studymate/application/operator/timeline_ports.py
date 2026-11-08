"""Narrow audited canonical timeline reads, no arbitrary telemetry query interface."""

import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.timeline import (
    OperatorAuditDetail,
    OperatorEventKind,
    OperatorTimelineEvent,
)
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorEventFilters:
    subject_account_id: UUID | None = None
    http_request_id: UUID | None = None
    action_id: UUID | None = None
    trace_id: str | None = field(default=None, repr=False)
    kind: OperatorEventKind | None = None
    occurred_from: datetime | None = None
    occurred_before: datetime | None = None

    def __post_init__(self) -> None:
        if self.trace_id is not None and (
            re.fullmatch(r"[0-9a-f]{32}", self.trace_id) is None or self.trace_id == "0" * 32
        ):
            raise ValueError("Timeline trace filter requires a bounded actual trace identifier")
        for at in (self.occurred_from, self.occurred_before):
            if at is not None:
                require_aware(at)
        if (
            self.occurred_from is not None
            and self.occurred_before is not None
            and self.occurred_from >= self.occurred_before
        ):
            raise ValueError("Timeline time filter must be a nonempty half-open interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.event-search.v1",
            str(self.subject_account_id or ""),
            str(self.http_request_id or ""),
            str(self.action_id or ""),
            self.trace_id or "",
            self.kind.value if self.kind is not None else "",
            self.occurred_from.astimezone(UTC).isoformat()
            if self.occurred_from is not None
            else "",
            self.occurred_before.astimezone(UTC).isoformat()
            if self.occurred_before is not None
            else "",
        )


@dataclass(frozen=True, slots=True)
class OperatorEventPosition:
    anchor_at: datetime
    occurred_at: datetime
    event_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_at)
        require_aware(self.occurred_at)
        if self.occurred_at > self.anchor_at:
            raise ValueError("Timeline position exceeds its search anchor, not a commit watermark")


@dataclass(frozen=True, slots=True)
class OperatorEventWindow:
    anchor_at: datetime
    before: OperatorEventPosition | None


class OperatorEventCursorCodec(Protocol):
    def encode_events(
        self, scope: OperatorCursorScope, fingerprint: bytes, position: OperatorEventPosition
    ) -> str: ...

    def decode_events(
        self, scope: OperatorCursorScope, fingerprint: bytes, token: str, now: datetime
    ) -> OperatorEventPosition: ...


class OperatorTimelineTransaction(OperatorAuditTransaction, Protocol):
    async def search_events(
        self, filters: OperatorEventFilters, window: OperatorEventWindow
    ) -> tuple[OperatorTimelineEvent, ...]:
        """At most50+lookahead, occurred_at/idDESC, bound search predicates not commit order."""
        ...

    async def operator_event(self, event_id: UUID) -> OperatorTimelineEvent | None: ...

    async def operator_audit(self, audit_id: UUID) -> OperatorAuditDetail | None: ...


class OperatorTimelineUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorTimelineTransaction]: ...
