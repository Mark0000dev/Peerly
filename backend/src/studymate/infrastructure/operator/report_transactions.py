"""Prepared report queries; actual current operator guard precedes every source read."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Nullable, and_, cast, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.types import String

from studymate.application.operator.report_ports import OperatorReportFilters, OperatorReportWindow
from studymate.domain.operator.profile_reports import (
    OPERATOR_REPORT_PAGE_SIZE,
    OperatorProfileReportSummary,
    OperatorReportDetail,
)
from studymate.infrastructure.operator.report_values import ReportListSource, report_detail_value
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlOperatorReportTransaction(SqlOperatorTransaction):
    async def search_profile_reports(
        self, filters: OperatorReportFilters, window: OperatorReportWindow
    ) -> tuple[OperatorProfileReportSummary, ...]:
        self.checked_access()
        # Deliberately select presence only, never private comment bodies for a metadata list.
        statement = (
            select(
                ProfileReportRecord.id,
                ProfileReportRecord.reporter_id,
                ProfileReportRecord.kind,
                ProfileReportRecord.category,
                ProfileReportRecord.submitted_at,
                ProfileReportRecord.comment.is_not(None),
                Nullable(func.coalesce(ProfileAccessRecord.id, MessageReportContextRecord.id)),
                Nullable(
                    func.coalesce(
                        ProfileAccessRecord.target_id, MessageReportContextRecord.target_id
                    )
                ),
            )
            .outerjoin(
                ProfileAccessRecord,
                and_(
                    ProfileAccessRecord.id == ProfileReportRecord.context_id,
                    ProfileAccessRecord.viewer_id == ProfileReportRecord.reporter_id,
                ),
            )
            .outerjoin(
                MessageReportContextRecord,
                and_(
                    MessageReportContextRecord.id == ProfileReportRecord.message_context_id,
                    MessageReportContextRecord.viewer_id == ProfileReportRecord.reporter_id,
                ),
            )
        )
        statement = statement.where(ProfileReportRecord.submitted_at <= window.anchor_at)
        if filters.reporter_id is not None:
            statement = statement.where(ProfileReportRecord.reporter_id == filters.reporter_id)
        if filters.target_id is not None:
            statement = statement.where(
                or_(
                    ProfileAccessRecord.target_id == filters.target_id,
                    MessageReportContextRecord.target_id == filters.target_id,
                )
            )
        if filters.context_id is not None:
            statement = statement.where(
                or_(
                    ProfileAccessRecord.id == filters.context_id,
                    MessageReportContextRecord.id == filters.context_id,
                )
            )
        if filters.category is not None:
            statement = statement.where(ProfileReportRecord.category == filters.category.value)
        if filters.submitted_from is not None:
            statement = statement.where(ProfileReportRecord.submitted_at >= filters.submitted_from)
        if filters.submitted_before is not None:
            statement = statement.where(ProfileReportRecord.submitted_at < filters.submitted_before)
        if window.before is not None:
            statement = statement.where(
                tuple_(ProfileReportRecord.submitted_at, ProfileReportRecord.id)
                < tuple_(window.before.submitted_at, window.before.report_id)
            )
        rows = (
            await self.session.execute(
                statement.order_by(
                    ProfileReportRecord.submitted_at.desc(), ProfileReportRecord.id.desc()
                ).limit(OPERATOR_REPORT_PAGE_SIZE + 1)
            )
        ).all()
        return tuple(ReportListSource(*row).value() for row in rows)

    async def operator_profile_report(self, report_id: UUID) -> OperatorReportDetail | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(
                    ProfileReportRecord,
                    Nullable(ProfileAccessRecord),
                    Nullable(ProductEventRecord),
                    Nullable(MessageReportContextRecord),
                    Nullable(MessageRecord.sent_at),
                )
                .outerjoin(
                    ProfileAccessRecord,
                    and_(
                        ProfileAccessRecord.id == ProfileReportRecord.context_id,
                        ProfileAccessRecord.viewer_id == ProfileReportRecord.reporter_id,
                    ),
                )
                .outerjoin(
                    MessageReportContextRecord,
                    and_(
                        MessageReportContextRecord.id == ProfileReportRecord.message_context_id,
                        MessageReportContextRecord.viewer_id == ProfileReportRecord.reporter_id,
                    ),
                )
                .outerjoin(MessageRecord, MessageRecord.id == MessageReportContextRecord.message_id)
                .outerjoin(
                    ProductEventRecord,
                    and_(
                        ProductEventRecord.kind == "report.created",
                        ProductEventRecord.account_id == ProfileReportRecord.reporter_id,
                        ProductEventRecord.report_id == ProfileReportRecord.id,
                        ProductEventRecord.occurrence_key
                        == "report:" + cast(ProfileReportRecord.id, String),
                    ),
                )
                .where(ProfileReportRecord.id == report_id)
            )
        ).one_or_none()
        return report_detail_value(*row) if row is not None else None


@dataclass(frozen=True, slots=True)
class SqlOperatorReportUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorReportTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorReportTransaction(session, self.recorder)
