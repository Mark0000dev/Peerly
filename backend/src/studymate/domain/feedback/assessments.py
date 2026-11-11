from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.feedback.interaction import InteractionEvidence
from studymate.domain.feedback.outcomes import StudyAnswer, StudyOutcomeRevision
from studymate.domain.text import optional_text, plain_text
from studymate.domain.time import require_aware

MAX_TEAM_NOTE_LENGTH = 1000


class StudyAgain(StrEnum):
    YES = "yes"
    MAYBE = "maybe"
    NO = "no"


class FeedbackDescriptor(StrEnum):
    EASY_TO_COMMUNICATE = "easy_to_communicate"
    PREPARED = "prepared"
    SUPPORTIVE = "supportive"


@dataclass(frozen=True, slots=True)
class FeedbackContent:
    again: StudyAgain
    descriptors: tuple[FeedbackDescriptor, ...] = ()
    team_note: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if len(self.descriptors) > len(FeedbackDescriptor) or len(set(self.descriptors)) != len(
            self.descriptors
        ):
            raise ValueError("Feedback descriptors must be distinct known selections")
        object.__setattr__(self, "descriptors", tuple(sorted(self.descriptors)))
        object.__setattr__(
            self,
            "team_note",
            optional_text(self.team_note, maximum=MAX_TEAM_NOTE_LENGTH, multiline=True),
        )


@dataclass(frozen=True, slots=True)
class FeedbackRevision:
    id: UUID
    version: int
    reviewer_id: UUID
    interaction: InteractionEvidence
    worked_confirmation: StudyOutcomeRevision
    content: FeedbackContent = field(repr=False)
    changed_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.changed_at)
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Feedback revision must be positive")
        self.interaction.conversation.pair.counterpart(self.reviewer_id)
        confirmation = self.worked_confirmation
        if (
            confirmation.actor_id != self.reviewer_id
            or confirmation.answer != StudyAnswer.YES
            or confirmation.conversation_id != self.interaction.conversation.id
            or confirmation.pair != self.interaction.conversation.pair
        ):
            raise ValueError("Feedback requires its actual reviewer's explicit worked-Yes source")

    @property
    def partner_id(self) -> UUID:
        return self.interaction.conversation.pair.counterpart(self.reviewer_id)

    @property
    def aggregate_eligible(self) -> bool:
        return self.interaction.two_way


class RemovalKind(StrEnum):
    FRAUDULENT = "fraudulent"
    ABUSIVE = "abusive"


@dataclass(frozen=True, slots=True)
class FeedbackRemoval:
    assessment_id: UUID
    source_version: int
    operator_id: UUID
    kind: RemovalKind
    reason: str = field(repr=False)
    removed_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.removed_at)
        if isinstance(self.source_version, bool) or self.source_version < 1:
            raise ValueError("Moderation removal requires an actual feedback source revision")
        object.__setattr__(
            self,
            "reason",
            plain_text(self.reason, minimum=1, maximum=MAX_TEAM_NOTE_LENGTH, multiline=True),
        )


@dataclass(frozen=True, slots=True)
class CurrentFeedback:
    revision: FeedbackRevision = field(repr=False)
    removal: FeedbackRemoval | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.removal is not None and (
            self.removal.assessment_id != self.revision.id
            or self.removal.source_version > self.revision.version
        ):
            raise ValueError("Feedback moderation source differs from its current revision")
