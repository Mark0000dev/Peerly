"""Raw retained feedback source facts, without student eligibility or content normalization."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.time import require_aware

OPERATOR_FEEDBACK_PAGE_SIZE = 50
MAX_OPERATOR_FEEDBACK_VERSION = (1 << 31) - 1
MAX_OPERATOR_FEEDBACK_TEXT = 1000
MAX_OPERATOR_FEEDBACK_DESCRIPTORS = 3
MAX_OPERATOR_FEEDBACK_DESCRIPTOR_LENGTH = 32
MAX_OPERATOR_FEEDBACK_AGAIN_LENGTH = 5
MAX_OPERATOR_FEEDBACK_ANSWER_LENGTH = 20
MAX_OPERATOR_FEEDBACK_KIND_LENGTH = 12


def require_feedback_version(version: int) -> None:
    if isinstance(version, bool) or not 1 <= version <= MAX_OPERATOR_FEEDBACK_VERSION:
        raise ValueError("Feedback inspection requires its actual bounded source version")


@dataclass(frozen=True, slots=True)
class OperatorFeedbackRoot:
    id: UUID
    reviewer_id: UUID
    partner_id: UUID
    conversation_id: UUID
    low_id: UUID
    high_id: UUID
    current_version: int
    current_removal_id: UUID | None
    current_changed_at: datetime

    def __post_init__(self) -> None:
        require_feedback_version(self.current_version)
        require_aware(self.current_changed_at)
        if self.low_id.int >= self.high_id.int or {self.reviewer_id, self.partner_id} != {
            self.low_id,
            self.high_id,
        }:
            raise ValueError("Feedback metadata differs from its actual participants")

    def includes(self, account_id: UUID) -> bool:
        return account_id in (self.reviewer_id, self.partner_id)


@dataclass(frozen=True, slots=True)
class OperatorFeedbackRevision:
    feedback_id: UUID
    version: int
    conversation_id: UUID
    reviewer_id: UUID
    partner_id: UUID
    low_id: UUID
    high_id: UUID
    worked_confirmation_id: UUID
    worked_answer: str
    low_message_id: UUID | None
    high_message_id: UUID | None
    again: str
    descriptors: tuple[str, ...]
    team_note: str | None = field(repr=False)
    changed_at: datetime
    origin: OperatorEventOrigin

    def __post_init__(self) -> None:
        require_feedback_version(self.version)
        require_aware(self.changed_at)
        if (
            len(self.descriptors) > MAX_OPERATOR_FEEDBACK_DESCRIPTORS
            or any(
                len(value) > MAX_OPERATOR_FEEDBACK_DESCRIPTOR_LENGTH for value in self.descriptors
            )
            or len(self.again) > MAX_OPERATOR_FEEDBACK_AGAIN_LENGTH
            or len(self.worked_answer) > MAX_OPERATOR_FEEDBACK_ANSWER_LENGTH
            or (
                self.team_note is not None
                and not 1 <= len(self.team_note) <= MAX_OPERATOR_FEEDBACK_TEXT
            )
        ):
            raise ValueError("Raw feedback exceeds its actual bounded source fields")
        # Descriptor order and note whitespace are retained exactly, no FeedbackContent decoder.


@dataclass(frozen=True, slots=True)
class OperatorFeedbackRemoval:
    id: UUID
    feedback_id: UUID
    source_version: int
    operator_id: UUID
    operator_access_version: int
    operator_access_active: bool
    kind: str
    reason: str = field(repr=False)
    removed_at: datetime
    origin: OperatorEventOrigin

    def __post_init__(self) -> None:
        require_feedback_version(self.source_version)
        require_feedback_version(self.operator_access_version)
        require_aware(self.removed_at)
        if (
            not 1 <= len(self.reason) <= MAX_OPERATOR_FEEDBACK_TEXT
            or len(self.kind) > MAX_OPERATOR_FEEDBACK_KIND_LENGTH
        ):
            raise ValueError("Raw feedback removal exceeds its actual bounded source fields")
        if not self.operator_access_active:
            raise ValueError("Feedback removal requires its recorded active grant source")
