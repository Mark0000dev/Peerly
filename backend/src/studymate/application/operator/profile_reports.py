"""Explicit privileged report reads with the actual canonical operator audit transaction."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.report_ports import (
    OperatorReportCursorCodec,
    OperatorReportFilters,
    OperatorReportPosition,
    OperatorReportUnitOfWork,
    OperatorReportWindow,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.profile_reports import (
    OPERATOR_REPORT_PAGE_SIZE,
    OperatorProfileReportSummary,
    OperatorReportDetail,
)


@dataclass(frozen=True, slots=True)
class OperatorProfileReportsPage:
    reports: tuple[OperatorProfileReportSummary, ...] = field(repr=False)
    next_cursor: str | None
    search_anchor_at: datetime


@dataclass(frozen=True, slots=True)
class SearchOperatorProfileReports:
    unit_of_work: OperatorReportUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorReportCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        filters: OperatorReportFilters,
        cursor: str | None = None,
    ) -> OperatorProfileReportsPage:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            now = await transaction.now()
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_reports(scope, digest, cursor, now)
                if cursor is not None
                else None
            )
            window = OperatorReportWindow(
                position.anchor_at if position is not None else now, position
            )
            rows = await transaction.search_profile_reports(filters, window)
            if len(rows) > OPERATOR_REPORT_PAGE_SIZE + 1:
                raise RuntimeError("Operator report search exceeded bounded source results")
            previous = (
                (position.submitted_at, position.report_id.int) if position is not None else None
            )
            for row in rows:
                current = row.submitted_at, row.id.int
                if row.submitted_at > window.anchor_at or (
                    previous is not None and current >= previous
                ):
                    raise RuntimeError(
                        "Operator report sources violate their anchored search ordering"
                    )
                previous = current
            visible = rows[:OPERATOR_REPORT_PAGE_SIZE]
            next_cursor = (
                self.cursor_codec.encode_reports(
                    scope,
                    digest,
                    OperatorReportPosition(
                        window.anchor_at, visible[-1].submitted_at, visible[-1].id
                    ),
                )
                if len(rows) > OPERATOR_REPORT_PAGE_SIZE
                else None
            )
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.SEARCH_REPORTS,
                    None,
                    tuple(
                        OperatorResourceRef(OperatorResourceKind.REPORT, row.id) for row in visible
                    ),
                    await transaction.now(),
                    OperatorAuditOutcome.SEARCH,
                    digest,
                )
            )
            await finish_operator(transaction, principal)
            return OperatorProfileReportsPage(visible, next_cursor, window.anchor_at)


@dataclass(frozen=True, slots=True)
class ReadOperatorProfileReport:
    unit_of_work: OperatorReportUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, report_id: UUID
    ) -> OperatorReportDetail | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            detail = await transaction.operator_profile_report(report_id)
            if detail is not None and detail.report.id != report_id:
                raise RuntimeError(
                    "Operator report detail differs from its actual requested source"
                )
            requested = OperatorResourceRef(OperatorResourceKind.REPORT, report_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_REPORT,
                    requested,
                    (requested,) if detail is not None else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ
                    if detail is not None
                    else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return detail
