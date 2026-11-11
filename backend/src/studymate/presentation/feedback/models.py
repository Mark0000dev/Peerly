"""Own structured feedback only; no public notes, reviewer lists or moderation evidence."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from studymate.application.feedback.reads import FeedbackPublication, OwnFeedbackContext
from studymate.domain.feedback.assessments import (
    MAX_TEAM_NOTE_LENGTH,
    FeedbackContent,
    FeedbackDescriptor,
    FeedbackRevision,
    StudyAgain,
)
from studymate.domain.feedback.outcomes import StudyAnswer, StudyOutcomeRevision, StudyPromptReceipt


class ClosedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StudyOutcomeBody(ClosedModel):
    answer: StudyAnswer
    expected_version: int = Field(strict=True, ge=0)


class FeedbackBody(ClosedModel):
    again: StudyAgain
    descriptors: tuple[FeedbackDescriptor, ...] = Field(
        default=(), max_length=len(FeedbackDescriptor)
    )
    team_note: str | None = Field(default=None, max_length=MAX_TEAM_NOTE_LENGTH, repr=False)
    expected_version: int = Field(strict=True, ge=0)

    def content(self) -> FeedbackContent:
        return FeedbackContent(self.again, self.descriptors, self.team_note)

    @model_validator(mode="after")
    def valid_content(self) -> Self:
        self.content()
        return self


class StudyPromptVisitBody(ClosedModel):
    pass


class StudyOutcomeResponse(ClosedModel):
    id: UUID
    conversation_id: UUID
    version: int = Field(ge=1)
    answer: StudyAnswer
    changed_at: datetime


class OwnStudyOutcomeResponse(ClosedModel):
    outcome: StudyOutcomeResponse | None


class FeedbackReceiptResponse(ClosedModel):
    id: UUID
    conversation_id: UUID
    version: int = Field(ge=1)
    again: StudyAgain
    descriptors: tuple[FeedbackDescriptor, ...] = Field(max_length=len(FeedbackDescriptor))
    team_note: str | None = Field(max_length=MAX_TEAM_NOTE_LENGTH, repr=False)
    changed_at: datetime
    worked_outcome_id: UUID
    worked_outcome_version: int = Field(ge=1)
    captured_public_eligibility: bool


class OwnFeedbackResponse(ClosedModel):
    current: FeedbackReceiptResponse | None = Field(repr=False)
    outcome: StudyOutcomeResponse | None
    can_submit: bool
    current_publication: FeedbackPublication | None
    submission_publication: FeedbackPublication | None


class OfferedStudyPromptResponse(ClosedModel):
    outcome: Literal["offered"] = "offered"
    receipt_id: UUID
    conversation_id: UUID
    offered_at: datetime


class NoStudyPromptResponse(ClosedModel):
    outcome: Literal["no_offer"] = "no_offer"


def outcome_response(value: StudyOutcomeRevision) -> StudyOutcomeResponse:
    return StudyOutcomeResponse(
        id=value.id,
        conversation_id=value.conversation_id,
        version=value.version,
        answer=value.answer,
        changed_at=value.changed_at,
    )


def feedback_response(value: FeedbackRevision) -> FeedbackReceiptResponse:
    return FeedbackReceiptResponse(
        id=value.id,
        conversation_id=value.interaction.conversation.id,
        version=value.version,
        again=value.content.again,
        descriptors=value.content.descriptors,
        team_note=value.content.team_note,
        changed_at=value.changed_at,
        worked_outcome_id=value.worked_confirmation.id,
        worked_outcome_version=value.worked_confirmation.version,
        captured_public_eligibility=value.aggregate_eligible,
    )


def context_response(value: OwnFeedbackContext) -> OwnFeedbackResponse:
    return OwnFeedbackResponse(
        current=feedback_response(value.current.revision) if value.current is not None else None,
        outcome=outcome_response(value.outcome) if value.outcome is not None else None,
        can_submit=value.can_submit,
        current_publication=value.current_publication,
        submission_publication=value.submission_publication,
    )


def prompt_response(
    value: StudyPromptReceipt | None,
) -> OfferedStudyPromptResponse | NoStudyPromptResponse:
    return (
        NoStudyPromptResponse()
        if value is None
        else OfferedStudyPromptResponse(
            receipt_id=value.id, conversation_id=value.conversation_id, offered_at=value.offered_at
        )
    )
