from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from studymate.application.report_moderation.history import ReportReviewHistoryPage
from studymate.domain.operator.profile_reports import OperatorReportKind
from studymate.domain.report_moderation.reviews import (
    MAX_REVIEW_VERSION,
    REVIEW_HISTORY_PAGE_SIZE,
    ReportReviewAction,
    ReportReviewReason,
    ReportReviewRevision,
)
from studymate.presentation.operator.models import ClosedModel


class ReviewReportBody(ClosedModel):
    expected_version: int = Field(ge=0, lt=MAX_REVIEW_VERSION, strict=True)
    action: ReportReviewAction
    reason: str = Field(min_length=1, max_length=1000, repr=False)

    @model_validator(mode="after")
    def documented_reason(self) -> Self:
        ReportReviewReason(self.reason)
        return self


class ReviewHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class ReportReviewResponse(ClosedModel):
    id: UUID
    report_id: UUID
    version: int
    previous_version: int | None
    action: ReportReviewAction
    reason: str = Field(repr=False)
    operator_id: UUID
    operator_access_version: int
    actor_session_id: UUID
    reviewed_at: AwareDatetime
    event_id: UUID
    http_request_id: UUID | None
    action_id: UUID | None
    trace_id: str | None
    span_id: str | None


class ReportReviewHistoryResponse(ClosedModel):
    report_id: UUID
    kind: OperatorReportKind
    reporter_id: UUID
    target_id: UUID
    context_id: UUID
    current: ReportReviewResponse | None = Field(repr=False)
    revisions: tuple[ReportReviewResponse, ...] = Field(
        max_length=REVIEW_HISTORY_PAGE_SIZE, repr=False
    )
    anchor_version: int
    next_cursor: str | None


def review_response(source: ReportReviewRevision) -> ReportReviewResponse:
    return ReportReviewResponse(
        id=source.id,
        report_id=source.report_id,
        version=source.version,
        previous_version=source.previous_version,
        action=source.action,
        reason=source.reason,
        operator_id=source.operator.account_id,
        operator_access_version=source.operator.version,
        actor_session_id=source.actor_session_id,
        reviewed_at=source.reviewed_at,
        event_id=source.event_id,
        http_request_id=source.origin.http_request_id,
        action_id=source.origin.action_id,
        trace_id=source.origin.trace_id,
        span_id=source.origin.span_id,
    )


def history_response(page: ReportReviewHistoryPage) -> ReportReviewHistoryResponse:
    return ReportReviewHistoryResponse(
        report_id=page.report.id,
        kind=page.report.kind,
        reporter_id=page.report.reporter_id,
        target_id=page.report.target_id,
        context_id=page.report.context_id,
        current=review_response(page.current) if page.current is not None else None,
        revisions=tuple(review_response(row) for row in page.revisions),
        anchor_version=page.anchor_version,
        next_cursor=page.next_cursor,
    )
