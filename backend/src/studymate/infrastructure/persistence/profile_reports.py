from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.safety.profile_reports import ReportBudget, ReportIntent
from studymate.domain.reports import (
    ProfileAccessContext,
    ProfileReport,
    ProfileVersionRefs,
    ReportCategory,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.product_events import record_profile_report_event
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportIntentRecord,
    ProfileReportRecord,
)
from studymate.infrastructure.persistence.transactions import open_transaction


def access_context_value(record: ProfileAccessRecord) -> ProfileAccessContext:
    return ProfileAccessContext(
        record.id,
        record.viewer_id,
        ProfileVersionRefs(
            record.target_id,
            record.profile_version,
            record.photo_version,
            record.goal_id,
            record.goal_version,
            record.help_version,
        ),
        record.issued_at,
    )


@dataclass(frozen=True, slots=True)
class SqlProfileReportTransaction(SqlIdentityTransaction):
    async def report_intent(self, actor_id: UUID, key: IntentKey) -> ReportIntent | None:
        record = await self.session.get(ProfileReportIntentRecord, (actor_id, key.value))
        return ReportIntent(record.fingerprint, record.report_id) if record is not None else None

    async def access_context(self, actor_id: UUID, context_id: UUID) -> ProfileAccessContext | None:
        record = await self.session.scalar(
            select(ProfileAccessRecord).where(
                ProfileAccessRecord.id == context_id, ProfileAccessRecord.viewer_id == actor_id
            )
        )
        return access_context_value(record) if record is not None else None

    async def own_report(self, actor_id: UUID, report_id: UUID) -> ProfileReport | None:
        row = (
            await self.session.execute(
                select(ProfileReportRecord, ProfileAccessRecord)
                .join(ProfileAccessRecord, ProfileAccessRecord.id == ProfileReportRecord.context_id)
                .where(
                    ProfileReportRecord.id == report_id,
                    ProfileReportRecord.reporter_id == actor_id,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        report, context = row
        return ProfileReport(
            report.id,
            report.reporter_id,
            access_context_value(context),
            ReportCategory(report.category),
            report.submitted_at,
            report.comment,
        )

    async def report_budget(self, actor_id: UUID, since: datetime) -> ReportBudget:
        count, oldest = (
            await self.session.execute(
                select(func.count(), func.min(ProfileReportRecord.submitted_at)).where(
                    ProfileReportRecord.reporter_id == actor_id,
                    ProfileReportRecord.submitted_at >= since,
                )
            )
        ).one()
        return ReportBudget(count, oldest)

    async def add_report(self, report: ProfileReport) -> None:
        self.session.add(
            ProfileReportRecord(
                id=report.id,
                reporter_id=report.reporter_id,
                context_id=report.context.id,
                category=report.category.value,
                comment=report.comment,
                submitted_at=report.submitted_at,
            )
        )
        await self.session.flush()
        await record_profile_report_event(self.session, report)

    async def remember_report_intent(
        self, actor_id: UUID, key: IntentKey, intent: ReportIntent, at: datetime
    ) -> None:
        self.session.add(
            ProfileReportIntentRecord(
                reporter_id=actor_id,
                key=key.value,
                fingerprint=intent.fingerprint,
                report_id=intent.report_id,
                created_at=at,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlProfileReportUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlProfileReportTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlProfileReportTransaction(session)
