"""Narrow retained-source reconstruction for authorized reads and same-transaction worker checks."""

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import Nullable, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.operator.report_triage_evidence import (
    ReportedProfileText,
    ReportTriageEvidenceUnavailableError,
    report_triage_evidence,
)
from studymate.domain.messaging import ConfirmedMessage, MessageContent
from studymate.domain.operator.profile_reports import OperatorProfileReportDetail
from studymate.domain.operator.report_triage import (
    ReportTriageEvidenceContext,
    ReportTriageSourcePreview,
)
from studymate.domain.relationships import AccountPair
from studymate.domain.report_moderation.reviews import ReviewReportSource
from studymate.infrastructure.operator.report_values import report_detail_value
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.profile_models import ProfileRevisionRecord
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)
from studymate.infrastructure.report_moderation.models import ReportReviewRevisionRecord


async def report_review_version(session: AsyncSession, report_id: UUID) -> int | None:
    return await session.scalar(
        select(func.max(ReportReviewRevisionRecord.version)).where(
            ReportReviewRevisionRecord.report_id == report_id
        )
    )


async def selected_report_preview(
    session: AsyncSession, source: ReviewReportSource
) -> ReportTriageSourcePreview:
    row = (
        await session.execute(
            select(
                ProfileReportRecord,
                Nullable(ProfileAccessRecord),
                Nullable(MessageReportContextRecord),
                Nullable(MessageRecord),
                Nullable(ProfileRevisionRecord.account_id),
                Nullable(ProfileRevisionRecord.version),
                Nullable(ProfileRevisionRecord.display_name),
                Nullable(ProfileRevisionRecord.about),
            )
            .select_from(ProfileReportRecord)
            .outerjoin(
                ProfileAccessRecord, ProfileAccessRecord.id == ProfileReportRecord.context_id
            )
            .outerjoin(
                MessageReportContextRecord,
                MessageReportContextRecord.id == ProfileReportRecord.message_context_id,
            )
            .outerjoin(MessageRecord, MessageRecord.id == MessageReportContextRecord.message_id)
            .outerjoin(
                ProfileRevisionRecord,
                and_(
                    ProfileRevisionRecord.account_id == ProfileAccessRecord.target_id,
                    ProfileRevisionRecord.version == ProfileAccessRecord.profile_version,
                ),
            )
            .where(ProfileReportRecord.id == source.id)
        )
    ).one_or_none()
    if row is None:
        raise RuntimeError("Locked triage report source disappeared")
    report, profile_context, message_context, message, account_id, version, name, about = row
    evidence = selected_report_evidence(
        source,
        SelectedReportRows(
            report,
            profile_context,
            message_context,
            message,
            ReportedProfileText(account_id, version, name, about)
            if account_id is not None and version is not None
            else None,
        ),
    )
    if evidence is None:
        return ReportTriageSourcePreview(source, None)
    # Retain the separate, final mutable freshness read, including advisory checks.
    return ReportTriageSourcePreview(
        source,
        ReportTriageEvidenceContext(
            source, await report_review_version(session, source.id), evidence
        ),
    )


@dataclass(frozen=True, slots=True)
class SelectedReportRows:
    report: ProfileReportRecord = field(repr=False)
    profile_context: ProfileAccessRecord | None = field(repr=False)
    message_context: MessageReportContextRecord | None = field(repr=False)
    message: MessageRecord | None = field(repr=False)
    profile: ReportedProfileText | None = field(repr=False)


def selected_report_evidence(source: ReviewReportSource, rows: SelectedReportRows) -> str | None:
    report, profile_context, message_context, message = (
        rows.report,
        rows.profile_context,
        rows.message_context,
        rows.message,
    )
    # Only selected evidence is consumed below. Canonical submission provenance is
    # not part of this projection; this helper never returns a report-detail DTO.
    detail = report_detail_value(
        report,
        profile_context,
        None,
        message_context,
        message.sent_at if message is not None else None,
    )
    if (
        detail.report.id,
        detail.report.kind,
        detail.report.target_id,
        detail.report.context_id,
    ) != (source.id, source.kind, source.target_id, source.context_id):
        raise RuntimeError("Triage projection differs from actual locked report/evidence")
    profile = None
    confirmed = None
    if isinstance(detail, OperatorProfileReportDetail):
        profile = rows.profile
    elif message is not None:
        image = detail.context.source.image
        if image is None or (message.image_id, message.image_version, message.image_attempt_id) != (
            image.id,
            image.version,
            image.attempt_id,
        ):
            raise RuntimeError("Triage selected image metadata differs from its actual message FK")
        confirmed = ConfirmedMessage(
            message.id,
            message.operation_id,
            message.conversation_id,
            AccountPair(message.low_id, message.high_id),
            message.author_id,
            message.client_message_id,
            message.sequence,
            MessageContent(message.text, message.image_id),
            message.sent_at,
        )
    try:
        return report_triage_evidence(detail, profile=profile, message=confirmed)
    except ReportTriageEvidenceUnavailableError:
        return None
