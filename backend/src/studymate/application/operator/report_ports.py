"""Bounded report-source reads under the existing same-transaction operator audit."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.profile_reports import (
    OperatorProfileReportSummary,
    OperatorReportDetail,
)
from studymate.domain.reports import ReportCategory
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorReportFilters:
    reporter_id: UUID | None = None
    target_id: UUID | None = None
    context_id: UUID | None = None
    category: ReportCategory | None = None
    submitted_from: datetime | None = None
    submitted_before: datetime | None = None

    def __post_init__(self) -> None:
        for at in (self.submitted_from, self.submitted_before):
            if at is not None:
                require_aware(at)
        if (
            self.submitted_from is not None
            and self.submitted_before is not None
            and self.submitted_from >= self.submitted_before
        ):
            raise ValueError("Report search requires a nonempty half-open time interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.profile-report-search.v1",
            str(self.reporter_id or ""),
            str(self.target_id or ""),
            str(self.context_id or ""),
            self.category.value if self.category is not None else "",
            self.submitted_from.astimezone(UTC).isoformat()
            if self.submitted_from is not None
            else "",
            self.submitted_before.astimezone(UTC).isoformat()
            if self.submitted_before is not None
            else "",
        )


@dataclass(frozen=True, slots=True)
class OperatorReportPosition:
    anchor_at: datetime
    submitted_at: datetime
    report_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_at)
        require_aware(self.submitted_at)
        if self.submitted_at > self.anchor_at:
            raise ValueError("Report search position exceeds its metadata search anchor")


@dataclass(frozen=True, slots=True)
class OperatorReportWindow:
    anchor_at: datetime
    before: OperatorReportPosition | None


class OperatorReportCursorCodec(Protocol):
    def encode_reports(
        self, scope: OperatorCursorScope, fingerprint: bytes, position: OperatorReportPosition
    ) -> str: ...

    def decode_reports(
        self, scope: OperatorCursorScope, fingerprint: bytes, token: str, now: datetime
    ) -> OperatorReportPosition: ...


class OperatorReportTransaction(OperatorAuditTransaction, Protocol):
    async def search_profile_reports(
        self, filters: OperatorReportFilters, window: OperatorReportWindow
    ) -> tuple[OperatorProfileReportSummary, ...]:
        """Metadata only, at most50+lookahead; no current student visibility or comment search."""
        ...

    async def operator_profile_report(self, report_id: UUID) -> OperatorReportDetail | None:
        """Actual retained comment/context and distinct known canonical submission origin."""
        ...


class OperatorReportUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorReportTransaction]: ...
