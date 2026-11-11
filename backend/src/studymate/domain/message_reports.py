"""Retained message evidence, never a discovery grant or a new-contact action."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from studymate.domain.relationships import AccountPair
from studymate.domain.reports import ReportCategory, report_comment
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class MessageImageRef:
    id: UUID
    version: int
    attempt_id: UUID

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Reported image requires its actual positive READY revision")


@dataclass(frozen=True, slots=True)
class ReportMessageSource:
    message_id: UUID
    conversation_id: UUID
    pair: AccountPair
    author_id: UUID
    client_message_id: UUID
    sent_at: datetime
    image: MessageImageRef | None

    def __post_init__(self) -> None:
        require_aware(self.sent_at)
        if self.author_id not in (self.pair.low, self.pair.high):
            raise ValueError("Report source author must be an actual conversation participant")


@dataclass(frozen=True, slots=True)
class MessageImageReportContext:
    """Immutable disclosed source reference; future reads still need current authority."""

    id: UUID
    reporter_id: UUID
    source: ReportMessageSource = field(repr=False)
    issued_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.issued_at)
        if self.reporter_id not in (self.source.pair.low, self.source.pair.high):
            raise ValueError("Message report context requires an actual participant reporter")
        if self.reporter_id == self.source.author_id:
            raise ValueError("Message image report must target the actual peer author")
        if self.source.image is None:
            raise ValueError("Message image report requires an actual confirmed image attachment")


@dataclass(frozen=True, slots=True)
class MessageImageReport:
    id: UUID
    reporter_id: UUID
    context: MessageImageReportContext = field(repr=False)
    category: ReportCategory
    submitted_at: datetime
    comment: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        require_aware(self.submitted_at)
        if self.reporter_id != self.context.reporter_id:
            raise ValueError("Message report must retain its actual context owner")
        object.__setattr__(self, "comment", report_comment(self.category, self.comment))
