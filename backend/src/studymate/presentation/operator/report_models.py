"""Closed retained-report output; references convey provenance, never media/read grants."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.operator.profile_reports import OperatorProfileReportsPage
from studymate.application.operator.report_ports import OperatorReportFilters
from studymate.domain.operator.profile_reports import (
    OPERATOR_REPORT_PAGE_SIZE,
    OperatorMessageImageReportDetail,
    OperatorProfileReportSummary,
    OperatorReportDetail,
    OperatorReportKind,
)
from studymate.domain.reports import MAX_REPORT_COMMENT_LENGTH, ReportCategory
from studymate.presentation.operator.models import ClosedModel
from studymate.presentation.operator.timeline_models import (
    OperatorEventOriginResponse,
    origin_response,
)


class OperatorReportQuery(ClosedModel):
    reporter_id: UUID | None = None
    target_id: UUID | None = None
    context_id: UUID | None = None
    category: ReportCategory | None = None
    submitted_from: AwareDatetime | None = None
    submitted_before: AwareDatetime | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)

    def filters(self) -> OperatorReportFilters:
        return OperatorReportFilters(
            self.reporter_id,
            self.target_id,
            self.context_id,
            self.category,
            self.submitted_from,
            self.submitted_before,
        )

    @model_validator(mode="after")
    def valid_filters(self) -> Self:
        self.filters()
        return self


class OperatorReportSummaryResponse(ClosedModel):
    kind: OperatorReportKind
    id: UUID
    reporter_id: UUID
    target_id: UUID
    context_id: UUID
    category: ReportCategory
    submitted_at: AwareDatetime
    has_comment: bool


class OperatorReportsResponse(ClosedModel):
    reports: tuple[OperatorReportSummaryResponse, ...] = Field(max_length=OPERATOR_REPORT_PAGE_SIZE)
    next_cursor: str | None
    search_anchor_at: AwareDatetime


class OperatorReportContextResponse(ClosedModel):
    kind: Literal["profile"]
    id: UUID
    reporter_id: UUID
    target_id: UUID
    profile_version: int = Field(ge=1)
    photo_version: int = Field(ge=1)
    goal_id: UUID | None
    goal_version: int | None = Field(ge=1)
    help_version: int | None = Field(ge=1)
    issued_at: AwareDatetime
    origin: OperatorEventOriginResponse


class OperatorMessageImageReportContextResponse(ClosedModel):
    kind: Literal["message_image"]
    id: UUID
    reporter_id: UUID
    target_id: UUID
    conversation_id: UUID
    message_id: UUID
    client_message_id: UUID
    image_id: UUID
    image_version: int = Field(ge=1)
    image_attempt_id: UUID
    message_sent_at: AwareDatetime
    issued_at: AwareDatetime
    origin: OperatorEventOriginResponse


class OperatorReportSubmissionResponse(ClosedModel):
    event_id: UUID
    report_id: UUID
    reporter_id: UUID
    occurred_at: AwareDatetime
    origin: OperatorEventOriginResponse


class OperatorReportDetailResponse(ClosedModel):
    report: OperatorReportSummaryResponse
    context: Annotated[
        OperatorReportContextResponse | OperatorMessageImageReportContextResponse,
        Field(discriminator="kind"),
    ]
    comment: str | None = Field(max_length=MAX_REPORT_COMMENT_LENGTH, repr=False)
    submission: OperatorReportSubmissionResponse | None


def report_summary_response(value: OperatorProfileReportSummary) -> OperatorReportSummaryResponse:
    return OperatorReportSummaryResponse(
        kind=value.kind,
        id=value.id,
        reporter_id=value.reporter_id,
        target_id=value.target_id,
        context_id=value.context_id,
        category=value.category,
        submitted_at=value.submitted_at,
        has_comment=value.has_comment,
    )


def reports_response(value: OperatorProfileReportsPage) -> OperatorReportsResponse:
    return OperatorReportsResponse(
        reports=tuple(report_summary_response(row) for row in value.reports),
        next_cursor=value.next_cursor,
        search_anchor_at=value.search_anchor_at,
    )


def context_response(
    value: OperatorReportDetail,
) -> OperatorReportContextResponse | OperatorMessageImageReportContextResponse:
    if isinstance(value, OperatorMessageImageReportDetail):
        context = value.context
        source = context.source
        image = source.image
        if image is None:
            raise RuntimeError("Operator report lost its actual retained image reference")
        return OperatorMessageImageReportContextResponse(
            kind="message_image",
            id=context.id,
            reporter_id=context.reporter_id,
            target_id=source.author_id,
            conversation_id=source.conversation_id,
            message_id=source.message_id,
            client_message_id=source.client_message_id,
            image_id=image.id,
            image_version=image.version,
            image_attempt_id=image.attempt_id,
            message_sent_at=source.sent_at,
            issued_at=context.issued_at,
            origin=origin_response(value.context_origin),
        )
    profile = value.context
    refs = profile.snapshot
    return OperatorReportContextResponse(
        kind="profile",
        id=profile.id,
        reporter_id=profile.viewer_id,
        target_id=refs.account_id,
        profile_version=refs.profile_version,
        photo_version=refs.photo_version,
        goal_id=refs.goal_id,
        goal_version=refs.goal_version,
        help_version=refs.help_version,
        issued_at=profile.issued_at,
        origin=origin_response(value.context_origin),
    )


def report_detail_response(value: OperatorReportDetail) -> OperatorReportDetailResponse:
    submission = value.submission
    return OperatorReportDetailResponse(
        report=report_summary_response(value.report),
        context=context_response(value),
        comment=value.comment,
        submission=OperatorReportSubmissionResponse(
            event_id=submission.event_id,
            report_id=submission.report_id,
            reporter_id=submission.reporter_id,
            occurred_at=submission.occurred_at,
            origin=origin_response(submission.origin),
        )
        if submission is not None
        else None,
    )
