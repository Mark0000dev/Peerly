"""Closed requested-target/correlation metadata queries over actual inspection sources."""

import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.audit import OperatorAction, OperatorResourceKind
from studymate.domain.operator.timeline import OperatorAuditDetail
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorAuditFilters:
    operator_id: UUID | None = None
    action: OperatorAction | None = None
    requested_kind: OperatorResourceKind | None = None
    requested_id: UUID | None = None
    http_request_id: UUID | None = None
    action_id: UUID | None = None
    trace_id: str | None = field(default=None, repr=False)
    occurred_from: datetime | None = None
    occurred_before: datetime | None = None

    def __post_init__(self) -> None:
        if self.requested_id is not None and self.requested_kind is None:
            raise ValueError("Audit requested ID requires its exact requested resource kind")
        if self.trace_id is not None and (
            re.fullmatch(r"[0-9a-f]{32}", self.trace_id) is None or self.trace_id == "0" * 32
        ):
            raise ValueError("Audit search requires a bounded nonzero trace identifier")
        for at in (self.occurred_from, self.occurred_before):
            if at is not None:
                require_aware(at)
        if (
            self.occurred_from is not None
            and self.occurred_before is not None
            and self.occurred_from >= self.occurred_before
        ):
            raise ValueError("Audit search requires a nonempty half-open time interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.audit-search.v1",
            str(self.operator_id or ""),
            self.action.value if self.action is not None else "",
            self.requested_kind.value if self.requested_kind is not None else "",
            str(self.requested_id or ""),
            str(self.http_request_id or ""),
            str(self.action_id or ""),
            self.trace_id or "",
            self.occurred_from.astimezone(UTC).isoformat() if self.occurred_from else "",
            self.occurred_before.astimezone(UTC).isoformat() if self.occurred_before else "",
        )

    def matches(self, detail: OperatorAuditDetail) -> bool:
        audit, origin = detail.audit, detail.origin
        return (
            (self.operator_id is None or audit.access.account_id == self.operator_id)
            and (self.action is None or audit.action == self.action)
            and (
                self.requested_kind is None
                or (audit.requested is not None and audit.requested.kind == self.requested_kind)
            )
            and (
                self.requested_id is None
                or (audit.requested is not None and audit.requested.id == self.requested_id)
            )
            and (self.http_request_id is None or origin.http_request_id == self.http_request_id)
            and (self.action_id is None or origin.action_id == self.action_id)
            and (self.trace_id is None or origin.trace_id == self.trace_id)
            and (self.occurred_from is None or audit.at >= self.occurred_from)
            and (self.occurred_before is None or audit.at < self.occurred_before)
        )


@dataclass(frozen=True, slots=True)
class OperatorAuditPosition:
    anchor_at: datetime
    occurred_at: datetime
    audit_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_at)
        require_aware(self.occurred_at)
        if self.occurred_at > self.anchor_at:
            raise ValueError("Audit cursor exceeds its time anchor, not a commit snapshot")


@dataclass(frozen=True, slots=True)
class OperatorAuditWindow:
    anchor_at: datetime
    before: OperatorAuditPosition | None

    def __post_init__(self) -> None:
        require_aware(self.anchor_at)
        if self.before is not None and self.before.anchor_at != self.anchor_at:
            raise ValueError("Audit window cannot rebind its cursor anchor")


class OperatorAuditCursorCodec(Protocol):
    def encode_audits(
        self, scope: OperatorCursorScope, fingerprint: bytes, position: OperatorAuditPosition
    ) -> str: ...
    def decode_audits(
        self, scope: OperatorCursorScope, fingerprint: bytes, token: str, now: datetime
    ) -> OperatorAuditPosition: ...


class OperatorAuditSearchTransaction(OperatorAuditTransaction, Protocol):
    async def search_audits(
        self, filters: OperatorAuditFilters, window: OperatorAuditWindow
    ) -> tuple[OperatorAuditDetail, ...]:
        """Actual audit+original grant,51 rows max; no content/private payload search."""
        ...


class OperatorAuditSearchUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorAuditSearchTransaction]: ...
