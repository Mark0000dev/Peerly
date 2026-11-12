"""Narrow retained-source reconstruction for authorized reads and same-transaction worker checks."""

from uuid import UUID

from sqlalchemy import func, select
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
    report = await session.get(ProfileReportRecord, source.id)
    if report is None:
        raise RuntimeError("Locked triage report source disappeared")
    profile_context = (
        await session.get(ProfileAccessRecord, report.context_id)
        if report.context_id is not None
        else None
    )
    message_context = (
        await session.get(MessageReportContextRecord, report.message_context_id)
        if report.message_context_id is not None
        else None
    )
    message = (
        await session.get(MessageRecord, message_context.message_id)
        if message_context is not None
        else None
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
        refs = detail.context.snapshot
        row = (
            await session.execute(
                select(
                    ProfileRevisionRecord.account_id,
                    ProfileRevisionRecord.version,
                    ProfileRevisionRecord.display_name,
                    ProfileRevisionRecord.about,
                ).where(
                    ProfileRevisionRecord.account_id == refs.account_id,
                    ProfileRevisionRecord.version == refs.profile_version,
                )
            )
        ).one_or_none()
        if row is not None:
            profile = ReportedProfileText(*row)
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
        evidence = report_triage_evidence(detail, profile=profile, message=confirmed)
    except ReportTriageEvidenceUnavailableError:
        return ReportTriageSourcePreview(source, None)
    return ReportTriageSourcePreview(
        source,
        ReportTriageEvidenceContext(
            source, await report_review_version(session, source.id), evidence
        ),
    )
