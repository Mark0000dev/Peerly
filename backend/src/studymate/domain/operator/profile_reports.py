"""Privileged retained report projections, not student submission or future access grants."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.message_reports import ReportMessageSource
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.reports import MAX_REPORT_COMMENT_LENGTH, ProfileAccessContext, ReportCategory
from studymate.domain.time import require_aware

OPERATOR_REPORT_PAGE_SIZE = 50


class OperatorReportKind(StrEnum):
    PROFILE = "profile"
    MESSAGE_IMAGE = "message_image"


@dataclass(frozen=True, slots=True)
class OperatorProfileReportSummary:
    id: UUID
    reporter_id: UUID
    target_id: UUID
    context_id: UUID
    category: ReportCategory
    submitted_at: datetime
    has_comment: bool
    kind: OperatorReportKind = OperatorReportKind.PROFILE

    def __post_init__(self) -> None:
        require_aware(self.submitted_at)
        if self.reporter_id == self.target_id:
            raise ValueError("Retained report must reference its actual distinct subject")
        if not isinstance(self.has_comment, bool):
            raise ValueError("Retained report comment presence must be an actual boolean")


@dataclass(frozen=True, slots=True)
class OperatorReportSubmission:
    event_id: UUID
    report_id: UUID
    reporter_id: UUID
    occurred_at: datetime
    origin: OperatorEventOrigin

    def __post_init__(self) -> None:
        require_aware(self.occurred_at)


@dataclass(frozen=True, slots=True)
class OperatorProfileReportDetail:
    report: OperatorProfileReportSummary
    context: ProfileAccessContext
    context_origin: OperatorEventOrigin
    comment: str | None = field(repr=False)
    submission: OperatorReportSubmission | None = None

    def __post_init__(self) -> None:
        if self.report.kind != OperatorReportKind.PROFILE:
            raise ValueError("Profile report detail requires its actual profile evidence kind")
        if (
            self.context.id != self.report.context_id
            or self.context.viewer_id != self.report.reporter_id
            or self.context.snapshot.account_id != self.report.target_id
        ):
            raise ValueError(
                "Retained report source context differs from its actual owned snapshot"
            )
        if self.report.has_comment != (self.comment is not None) or (
            self.comment is not None and not 1 <= len(self.comment) <= MAX_REPORT_COMMENT_LENGTH
        ):
            raise ValueError("Retained report comment differs from its actual bounded stored value")
        if self.report.category == ReportCategory.OTHER and self.comment is None:
            raise ValueError("Retained Other report lost its original required explanation")
        if self.submission is not None and (
            self.submission.report_id != self.report.id
            or self.submission.reporter_id != self.report.reporter_id
        ):
            raise ValueError("Retained submission event differs from its actual report source")
        # No text normalization or cross-timestamp order: IDs/FKs prove retained source ownership.


@dataclass(frozen=True, slots=True)
class OperatorMessageImageReportContext:
    """Retained FK evidence only, never a future participant or profile-read grant."""

    id: UUID
    reporter_id: UUID
    source: ReportMessageSource = field(repr=False)
    issued_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.issued_at)
        if (
            self.source.image is None
            or self.reporter_id == self.source.author_id
            or self.reporter_id not in (self.source.pair.low, self.source.pair.high)
        ):
            raise ValueError("Retained message image context lost its actual peer/participant FK")


@dataclass(frozen=True, slots=True)
class OperatorMessageImageReportDetail:
    report: OperatorProfileReportSummary
    context: OperatorMessageImageReportContext
    context_origin: OperatorEventOrigin
    comment: str | None = field(repr=False)
    submission: OperatorReportSubmission | None = None

    def __post_init__(self) -> None:
        if self.report.kind != OperatorReportKind.MESSAGE_IMAGE or (
            self.context.id,
            self.context.reporter_id,
            self.context.source.author_id,
        ) != (self.report.context_id, self.report.reporter_id, self.report.target_id):
            raise ValueError("Retained image report differs from its actual owned message context")
        if self.report.has_comment != (self.comment is not None) or (
            self.comment is not None and not 1 <= len(self.comment) <= MAX_REPORT_COMMENT_LENGTH
        ):
            raise ValueError("Retained report comment differs from its actual bounded stored value")
        if self.report.category == ReportCategory.OTHER and self.comment is None:
            raise ValueError("Retained Other report lost its original required explanation")
        if self.submission is not None and (
            self.submission.report_id != self.report.id
            or self.submission.reporter_id != self.report.reporter_id
        ):
            raise ValueError("Retained submission event differs from its actual report source")


type OperatorReportDetail = OperatorProfileReportDetail | OperatorMessageImageReportDetail
