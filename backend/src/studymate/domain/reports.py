"""Selected profile references and reports; reporting never applies a block."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.text import optional_text
from studymate.domain.time import require_aware

MAX_REPORT_COMMENT_LENGTH = 1000


class ReportCategory(StrEnum):
    IMPERSONATION = "impersonation"
    HARASSMENT = "harassment"
    INAPPROPRIATE_CONTENT = "inappropriate_content"
    SPAM = "spam"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ProfileVersionRefs:
    account_id: UUID
    profile_version: int
    photo_version: int
    goal_id: UUID | None
    goal_version: int | None
    help_version: int | None

    def __post_init__(self) -> None:
        versions = (self.profile_version, self.photo_version)
        if any(isinstance(version, bool) or version < 1 for version in versions):
            raise ValueError("Reported profile/photo references need positive revisions")
        if (self.goal_id is None) != (self.goal_version is None):
            raise ValueError("Reported goal reference requires both identity and revision")
        for version in (self.goal_version, self.help_version):
            if version is not None and (isinstance(version, bool) or version < 1):
                raise ValueError("Reported study context requires positive revisions")


@dataclass(frozen=True, slots=True)
class ProfileAccessContext:
    """A server-issued disclosure reference, never permission for a future read."""

    id: UUID
    viewer_id: UUID
    snapshot: ProfileVersionRefs
    issued_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.issued_at)
        if self.viewer_id == self.snapshot.account_id:
            raise ValueError("Peer report context cannot target the viewer")


@dataclass(frozen=True, slots=True)
class ProfileReport:
    id: UUID
    reporter_id: UUID
    context: ProfileAccessContext = field(repr=False)
    category: ReportCategory
    submitted_at: datetime
    comment: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        require_aware(self.submitted_at)
        if self.reporter_id != self.context.viewer_id:
            raise ValueError("Report context belongs to another actor")
        if self.submitted_at < self.context.issued_at:
            raise ValueError("Report cannot precede the issued access context")
        object.__setattr__(self, "comment", report_comment(self.category, self.comment))


def report_comment(category: ReportCategory, value: str | None) -> str | None:
    comment = optional_text(value, maximum=MAX_REPORT_COMMENT_LENGTH, multiline=True)
    if category == ReportCategory.OTHER and comment is None:
        raise ValueError("Other report category requires an explanation")
    return comment
