from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from studymate.application.operator.report_ports import OperatorReportFilters, OperatorReportWindow
from studymate.domain.operator.profile_reports import (
    OPERATOR_REPORT_PAGE_SIZE,
    OperatorProfileReportDetail,
    OperatorProfileReportSummary,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.reports import ProfileAccessContext, ProfileVersionRefs, ReportCategory
from tests.unit.identity_store import NOW
from tests.unit.operator.store import Store


def report(*, report_id: UUID | None = None) -> OperatorProfileReportDetail:
    reporter, target, context = uuid4(), uuid4(), uuid4()
    summary = OperatorProfileReportSummary(
        report_id or uuid4(),
        reporter,
        target,
        context,
        ReportCategory.HARASSMENT,
        NOW - timedelta(hours=1),
        True,
    )
    source = ProfileAccessContext(
        context, reporter, ProfileVersionRefs(target, 1, 1, None, None, None), NOW
    )
    return OperatorProfileReportDetail(
        summary, source, OperatorEventOrigin(), " Exact private retained comment "
    )


class ReportStore(Store):
    def __init__(self) -> None:
        super().__init__()
        source = report()
        self.reports: tuple[OperatorProfileReportSummary, ...] = (source.report,)
        self.details_by_report = {source.report.id: source}
        self.report_rows: tuple[OperatorProfileReportSummary, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["ReportStore"]:
        async with Store.transaction(self):
            yield self

    async def search_profile_reports(
        self, filters: OperatorReportFilters, window: OperatorReportWindow
    ) -> tuple[OperatorProfileReportSummary, ...]:
        self.queried()
        if self.report_rows is not None:
            return self.report_rows
        rows = tuple(
            row
            for row in self.reports
            if row.submitted_at <= window.anchor_at
            and (
                window.before is None
                or (row.submitted_at, row.id.int)
                < (window.before.submitted_at, window.before.report_id.int)
            )
            and (filters.reporter_id is None or row.reporter_id == filters.reporter_id)
            and (filters.target_id is None or row.target_id == filters.target_id)
            and (filters.context_id is None or row.context_id == filters.context_id)
            and (filters.category is None or row.category == filters.category)
            and (filters.submitted_from is None or row.submitted_at >= filters.submitted_from)
            and (filters.submitted_before is None or row.submitted_at < filters.submitted_before)
        )
        return tuple(sorted(rows, key=lambda row: (row.submitted_at, row.id.int), reverse=True))[
            : OPERATOR_REPORT_PAGE_SIZE + 1
        ]

    async def operator_profile_report(self, report_id: UUID) -> OperatorProfileReportDetail | None:
        self.queried()
        return self.details_by_report.get(report_id)
