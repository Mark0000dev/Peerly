"""Human report decisions retain exact reasons and original administrative proof."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.profile_reports import OperatorReportKind
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.text import plain_text
from studymate.domain.time import require_aware

MAX_REVIEW_REASON_CHARACTERS = 1000
MAX_REVIEW_VERSION = (1 << 31) - 1
REVIEW_HISTORY_PAGE_SIZE = 50


class ReportReviewAction(StrEnum):
    DISMISS = "dismiss"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class ReportReviewReason:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not 1 <= len(self.value) <= MAX_REVIEW_REASON_CHARACTERS or not self.value.strip():
            raise ValueError("Report review requires a bounded documented reason")
        plain_text(self.value, minimum=1, maximum=MAX_REVIEW_REASON_CHARACTERS, multiline=True)


@dataclass(frozen=True, slots=True)
class ReviewReportSource:
    id: UUID
    kind: OperatorReportKind
    reporter_id: UUID
    target_id: UUID
    context_id: UUID


@dataclass(frozen=True, slots=True)
class ReportReviewRevision:
    id: UUID
    report_id: UUID
    version: int
    previous_version: int | None
    action: ReportReviewAction
    reason: str = field(repr=False)
    operator: OperatorAccess
    actor_session_id: UUID
    reviewed_at: datetime
    event_id: UUID
    origin: OperatorEventOrigin = field(default_factory=OperatorEventOrigin)

    def __post_init__(self) -> None:
        require_aware(self.reviewed_at)
        if (
            isinstance(self.version, bool)
            or not 1 <= self.version <= MAX_REVIEW_VERSION
            or self.previous_version != (self.version - 1 if self.version > 1 else None)
        ):
            raise ValueError("Report review requires consecutive bounded source versions")
        if not self.operator.is_active(self.reviewed_at):
            raise ValueError("Report review requires its original active operator grant")
        if not self.reason.strip():
            raise ValueError("Report review requires an actual retained reason")

    @property
    def occurrence_key(self) -> str:
        return f"report-review:{self.id}"
