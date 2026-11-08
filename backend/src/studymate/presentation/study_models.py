from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from studymate.application.profiles.goals import SavedGoal
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.domain.study_context import (
    MAX_CONTEXT_LENGTH,
    MAX_HELP_SUBJECTS,
    MAX_TOPIC_LENGTH,
    CanonicalSubjectRef,
    CustomSubjectRef,
    HelpSubject,
    HelpSubjects,
)
from studymate.domain.text import optional_text


def _optional(value: object, maximum: int, *, multiline: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("A plain-text value is required")
    return optional_text(value, maximum=maximum, multiline=multiline)


class CanonicalSubjectRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["canonical"]
    id: UUID


class CustomSubjectRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["custom"]
    label: str = Field(min_length=1, max_length=MAX_TOPIC_LENGTH, repr=False)

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("A custom subject must be plain text")
        return CustomSubjectRef(value).label


SubjectRequest = Annotated[
    CanonicalSubjectRequest | CustomSubjectRequest, Field(discriminator="kind")
]


class SaveGoalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    subject: SubjectRequest
    topic: str | None = Field(default=None, max_length=MAX_TOPIC_LENGTH, repr=False)
    context: str | None = Field(default=None, max_length=MAX_CONTEXT_LENGTH, repr=False)
    shared_learning: bool = Field(default=False, strict=True)
    expected_goal_id: UUID | None = None
    expected_version: int = Field(strict=True, ge=0)

    @field_validator("topic", mode="before")
    @classmethod
    def normalize_topic(cls, value: object) -> str | None:
        return _optional(value, MAX_TOPIC_LENGTH)

    @field_validator("context", mode="before")
    @classmethod
    def normalize_context(cls, value: object) -> str | None:
        return _optional(value, MAX_CONTEXT_LENGTH, multiline=True)


class CompleteGoalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    goal_id: UUID
    expected_version: int = Field(strict=True, ge=1)


class CanonicalSubjectResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["canonical"] = "canonical"
    id: UUID
    label: str = Field(repr=False)


class CustomSubjectResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["custom"] = "custom"
    label: str = Field(repr=False)


class GoalResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    version: int
    subject: Annotated[
        CanonicalSubjectResponse | CustomSubjectResponse, Field(discriminator="kind")
    ]
    topic: str | None = Field(repr=False)
    context: str | None = Field(repr=False)
    shared_learning: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class OwnGoalResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    goal: GoalResponse | None


class HelpSubjectRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    subject_id: UUID
    topic_note: str | None = Field(default=None, max_length=MAX_TOPIC_LENGTH, repr=False)

    @field_validator("topic_note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> str | None:
        return _optional(value, MAX_TOPIC_LENGTH)


class SaveHelpRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    subjects: tuple[HelpSubjectRequest, ...] = Field(max_length=MAX_HELP_SUBJECTS)
    expected_version: int = Field(strict=True, ge=0)

    @field_validator("subjects")
    @classmethod
    def validate_selections(
        cls, values: tuple[HelpSubjectRequest, ...]
    ) -> tuple[HelpSubjectRequest, ...]:
        HelpSubjects(tuple(HelpSubject(value.subject_id, value.topic_note) for value in values))
        return values


class HelpSubjectResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    subject_id: UUID
    label: str = Field(repr=False)
    topic_note: str | None = Field(repr=False)


class HelpResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int
    subjects: tuple[HelpSubjectResponse, ...]
    saved_at: datetime


class OwnHelpResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    selection: HelpResponse | None


def goal_response(value: SavedGoal) -> GoalResponse:
    subject = value.goal.content.subject
    return GoalResponse(
        id=value.goal.id,
        version=value.goal.version,
        subject=CanonicalSubjectResponse(id=subject.id, label=value.subject_label)
        if isinstance(subject, CanonicalSubjectRef)
        else CustomSubjectResponse(label=subject.label),
        topic=value.goal.content.topic,
        context=value.goal.content.context,
        shared_learning=value.goal.content.shared_learning,
        created_at=value.goal.created_at,
        updated_at=value.goal.updated_at,
        completed_at=value.goal.completed_at,
    )


def help_response(value: SavedHelpSubjects) -> HelpResponse:
    return HelpResponse(
        version=value.revision.version,
        subjects=tuple(
            HelpSubjectResponse(
                subject_id=subject.subject_id, label=label, topic_note=subject.topic_note
            )
            for subject, label in zip(value.revision.subjects.values, value.labels, strict=True)
        ),
        saved_at=value.revision.saved_at,
    )
