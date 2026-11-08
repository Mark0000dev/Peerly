"""Bounded immutable business snapshots, never prompts or telemetry payloads."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import GoalSnapshot, HelpSnapshot, RequestContext
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    GoalContent,
    HelpRevision,
    HelpSubject,
    HelpSubjects,
    StudyGoal,
)

MAX_SNAPSHOT_BYTES = 32768


class StoredRequestSnapshotError(RuntimeError):
    pass


class GoalDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    id: UUID
    account_id: UUID
    version: int = Field(strict=True, ge=1)
    subject_id: UUID
    subject_label: str = Field(strict=True, min_length=1, max_length=80, repr=False)
    topic: str | None = Field(default=None, strict=True, max_length=80, repr=False)
    context: str | None = Field(default=None, strict=True, max_length=240, repr=False)
    shared_learning: bool = Field(strict=True)
    created_at: datetime
    updated_at: datetime

    def value(self) -> GoalSnapshot:
        return GoalSnapshot(
            StudyGoal(
                self.id,
                self.account_id,
                self.version,
                GoalContent(
                    CanonicalSubjectRef(self.subject_id),
                    self.topic,
                    self.context,
                    self.shared_learning,
                ),
                self.created_at,
                self.updated_at,
            ),
            self.subject_label,
        )

    @classmethod
    def of(cls, snapshot: GoalSnapshot) -> Self:
        goal = snapshot.goal
        subject = goal.content.canonical_subject_id
        if subject is None:
            raise StoredRequestSnapshotError("Request goal is not canonical")
        return cls(
            id=goal.id,
            account_id=goal.account_id,
            version=goal.version,
            subject_id=subject,
            subject_label=snapshot.subject_label,
            topic=goal.content.topic,
            context=goal.content.context,
            shared_learning=goal.content.shared_learning,
            created_at=goal.created_at,
            updated_at=goal.updated_at,
        )


class HelpSelectionDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    subject_id: UUID
    label: str = Field(strict=True, min_length=1, max_length=80, repr=False)
    topic_note: str | None = Field(default=None, strict=True, max_length=80, repr=False)


class HelpDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    account_id: UUID
    version: int = Field(strict=True, ge=1)
    saved_at: datetime
    selections: tuple[HelpSelectionDocument, ...] = Field(max_length=5, repr=False)

    def value(self) -> HelpSnapshot:
        return HelpSnapshot(
            HelpRevision(
                self.account_id,
                self.version,
                HelpSubjects(
                    tuple(HelpSubject(item.subject_id, item.topic_note) for item in self.selections)
                ),
                self.saved_at,
            ),
            tuple(item.label for item in self.selections),
        )

    @classmethod
    def of(cls, snapshot: HelpSnapshot) -> Self:
        revision = snapshot.revision
        return cls(
            account_id=revision.account_id,
            version=revision.version,
            saved_at=revision.saved_at,
            selections=tuple(
                HelpSelectionDocument(
                    subject_id=item.subject_id, label=label, topic_note=item.topic_note
                )
                for item, label in zip(revision.subjects.values, snapshot.labels, strict=True)
            ),
        )


class ContextDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    sender_id: UUID
    recipient_id: UUID
    mode: DiscoveryMode
    sender_goal: GoalDocument | None = Field(default=None, repr=False)
    recipient_goal: GoalDocument | None = Field(default=None, repr=False)
    sender_help: HelpDocument | None = Field(default=None, repr=False)
    recipient_help: HelpDocument | None = Field(default=None, repr=False)

    def value(self) -> RequestContext:
        return RequestContext(
            self.sender_id,
            self.recipient_id,
            self.mode,
            self.sender_goal.value() if self.sender_goal is not None else None,
            self.recipient_goal.value() if self.recipient_goal is not None else None,
            self.sender_help.value() if self.sender_help is not None else None,
            self.recipient_help.value() if self.recipient_help is not None else None,
        )

    @model_validator(mode="after")
    def valid_sources(self) -> Self:
        self.value()
        return self

    @classmethod
    def of(cls, context: RequestContext) -> Self:
        return cls(
            sender_id=context.sender_id,
            recipient_id=context.recipient_id,
            mode=context.mode,
            sender_goal=GoalDocument.of(context.sender_goal)
            if context.sender_goal is not None
            else None,
            recipient_goal=GoalDocument.of(context.recipient_goal)
            if context.recipient_goal is not None
            else None,
            sender_help=HelpDocument.of(context.sender_help)
            if context.sender_help is not None
            else None,
            recipient_help=HelpDocument.of(context.recipient_help)
            if context.recipient_help is not None
            else None,
        )


class SnapshotDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def real_version(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Snapshot version must be an integer")
        return value

    context: ContextDocument = Field(repr=False)


def encode_context(context: RequestContext) -> str:
    raw = SnapshotDocument(schema_version=1, context=ContextDocument.of(context)).model_dump_json()
    if len(raw.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise StoredRequestSnapshotError("Request snapshot exceeds storage bound")
    return raw


def decode_context(raw: str | bytes) -> RequestContext:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(encoded) > MAX_SNAPSHOT_BYTES:
            raise StoredRequestSnapshotError("Request snapshot exceeds storage bound")
        return SnapshotDocument.model_validate_json(encoded, strict=True).context.value()
    except (ValidationError, UnicodeError):
        # Pydantic raw errors can embed private source text; never chain/forward them.
        raise StoredRequestSnapshotError("Stored request snapshot does not conform") from None
