"""Retained unified report evidence; never fabricate profile versions for an image report."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from studymate.domain.message_reports import MessageImageRef, ReportMessageSource
from studymate.domain.operator.profile_reports import (
    OperatorMessageImageReportContext,
    OperatorMessageImageReportDetail,
    OperatorProfileReportDetail,
    OperatorProfileReportSummary,
    OperatorReportDetail,
    OperatorReportKind,
    OperatorReportSubmission,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.relationships import AccountPair
from studymate.domain.reports import ReportCategory
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.profile_reports import access_context_value
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)


@dataclass(frozen=True, slots=True)
class ReportListSource:
    id: UUID
    reporter_id: UUID
    kind: str
    category: str
    submitted_at: datetime
    has_comment: bool
    context_id: UUID | None
    target_id: UUID | None

    def value(self) -> OperatorProfileReportSummary:
        kind = OperatorReportKind(self.kind)
        context_id, target_id = self.context_id, self.target_id
        if context_id is None or target_id is None:
            raise RuntimeError("Retained report list lost its actual discriminated owned context")
        return OperatorProfileReportSummary(
            self.id,
            self.reporter_id,
            target_id,
            context_id,
            ReportCategory(self.category),
            self.submitted_at,
            self.has_comment,
            kind,
        )


def submission_value(
    report: ProfileReportRecord,
    submission: ProductEventRecord | None,
) -> OperatorReportSubmission | None:
    if submission is None:
        return None
    if (
        submission.kind != "report.created"
        or submission.report_id != report.id
        or submission.account_id != report.reporter_id
        or submission.occurrence_key != f"report:{report.id}"
    ):
        raise RuntimeError("Report submission origin lost its actual owned canonical event")
    return OperatorReportSubmission(
        submission.id,
        report.id,
        report.reporter_id,
        submission.occurred_at,
        OperatorEventOrigin(
            submission.request_id, submission.action_id, submission.trace_id, submission.span_id
        ),
    )


def report_detail_value(
    report: ProfileReportRecord,
    context: ProfileAccessRecord | None,
    submission: ProductEventRecord | None,
    message_context: MessageReportContextRecord | None = None,
    message_sent_at: datetime | None = None,
) -> OperatorReportDetail:
    kind = OperatorReportKind(report.kind)
    event = submission_value(report, submission)
    if kind == OperatorReportKind.PROFILE:
        if (
            context is None
            or report.context_id != context.id
            or message_context is not None
            or report.message_context_id is not None
        ):
            raise RuntimeError("Profile report lost its actual profile-only retained context")
        return OperatorProfileReportDetail(
            OperatorProfileReportSummary(
                report.id,
                report.reporter_id,
                context.target_id,
                context.id,
                ReportCategory(report.category),
                report.submitted_at,
                report.comment is not None,
                kind,
            ),
            access_context_value(context),
            OperatorEventOrigin(
                context.request_id, context.action_id, context.trace_id, context.span_id
            ),
            report.comment,
            event,
        )
    if (
        message_context is None
        or report.message_context_id != message_context.id
        or message_sent_at is None
        or context is not None
        or report.context_id is not None
    ):
        raise RuntimeError("Image report lost its actual message-only retained context")
    source = ReportMessageSource(
        message_context.message_id,
        message_context.conversation_id,
        AccountPair(message_context.low_id, message_context.high_id),
        message_context.target_id,
        message_context.client_message_id,
        message_sent_at,
        MessageImageRef(
            message_context.image_id,
            message_context.image_version,
            message_context.image_attempt_id,
        ),
    )
    return OperatorMessageImageReportDetail(
        OperatorProfileReportSummary(
            report.id,
            report.reporter_id,
            message_context.target_id,
            message_context.id,
            ReportCategory(report.category),
            report.submitted_at,
            report.comment is not None,
            kind,
        ),
        OperatorMessageImageReportContext(
            message_context.id, message_context.viewer_id, source, message_context.issued_at
        ),
        OperatorEventOrigin(
            message_context.request_id,
            message_context.action_id,
            message_context.trace_id,
            message_context.span_id,
        ),
        report.comment,
        event,
    )
