"""UNREGISTERED owner0037 proposal; do not collect before paired main DDL READY.

Human-message owner FKs require main's pending messages(id,conversation_id,author_id)
unique constraint. Models use application Base; no separate registry or create_all.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


def origin_checks() -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL "
            "AND span_id IS NULL)",
            name="origin_request_context",
        ),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND "
            "span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != "
            "repeat('0',32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != "
            "repeat('0',16))",
            name="origin_trace_pair",
        ),
    )


class StudyOutcomeRecord(Base):
    __tablename__ = "study_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "actor_id",
            "low_id",
            "high_id",
            name="uq_study_outcomes_participants",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "actor_id", "current_version"],
            [
                "study_outcome_revisions.conversation_id",
                "study_outcome_revisions.actor_id",
                "study_outcome_revisions.version",
            ],
            name="fk_study_outcomes_current",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "low_id < high_id AND actor_id IN (low_id,high_id)", name="participant_actor"
        ),
        CheckConstraint("current_version > 0", name="positive_revision"),
    )
    conversation_id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    current_version: Mapped[int] = mapped_column()


class StudyOutcomeRevisionRecord(Base):
    __tablename__ = "study_outcome_revisions"
    __table_args__ = (
        UniqueConstraint(
            "id", "conversation_id", "actor_id", name="uq_study_outcome_revisions_owned"
        ),
        UniqueConstraint(
            "conversation_id", "actor_id", "version", name="uq_study_outcome_revisions_version"
        ),
        UniqueConstraint(
            "id",
            "conversation_id",
            "actor_id",
            "answer",
            name="uq_study_outcome_revisions_worked_source",
        ),
        UniqueConstraint(
            "id",
            "conversation_id",
            "actor_id",
            "version",
            "answer",
            name="uq_study_outcome_revisions_event_source",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "actor_id", "low_id", "high_id"],
            [
                "study_outcomes.conversation_id",
                "study_outcomes.actor_id",
                "study_outcomes.low_id",
                "study_outcomes.high_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="positive_revision"),
        CheckConstraint("answer IN ('yes','not_yet','did_not_work_out')", name="bounded_answer"),
        Index(
            "ix_study_outcome_revisions_window",
            "conversation_id",
            "actor_id",
            "changed_at",
            "version",
        ),
        *origin_checks(),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column()
    actor_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column()
    answer: Mapped[str] = mapped_column(String(20))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class PeerFeedbackRecord(Base):
    __tablename__ = "peer_feedback"
    __table_args__ = (
        UniqueConstraint("reviewer_id", "partner_id", name="uq_peer_feedback_ordered_pair"),
        UniqueConstraint(
            "id",
            "conversation_id",
            "reviewer_id",
            "partner_id",
            "low_id",
            "high_id",
            name="uq_peer_feedback_owned_source",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["id", "current_version"],
            ["peer_feedback_revisions.feedback_id", "peer_feedback_revisions.version"],
            name="fk_peer_feedback_current",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["current_removal_id", "id"],
            ["peer_feedback_removals.id", "peer_feedback_removals.feedback_id"],
            name="fk_peer_feedback_current_removal",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "low_id < high_id AND ((reviewer_id=low_id AND partner_id=high_id) OR "
            "(reviewer_id=high_id AND partner_id=low_id))",
            name="ordered_participants",
        ),
        CheckConstraint("current_version > 0", name="positive_revision"),
        Index("ix_peer_feedback_partner", "partner_id", "reviewer_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    partner_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    conversation_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    current_version: Mapped[int] = mapped_column()
    current_removal_id: Mapped[UUID | None] = mapped_column()


class PeerFeedbackRevisionRecord(Base):
    __tablename__ = "peer_feedback_revisions"
    __table_args__ = (
        UniqueConstraint(
            "feedback_id",
            "version",
            "reviewer_id",
            "conversation_id",
            name="uq_peer_feedback_revisions_intent_source",
        ),
        UniqueConstraint(
            "feedback_id", "version", "reviewer_id", name="uq_peer_feedback_revisions_owned"
        ),
        UniqueConstraint(
            "feedback_id",
            "version",
            "reviewer_id",
            "again",
            name="uq_peer_feedback_revisions_event_source",
        ),
        ForeignKeyConstraint(
            ["feedback_id", "conversation_id", "reviewer_id", "partner_id", "low_id", "high_id"],
            [
                "peer_feedback.id",
                "peer_feedback.conversation_id",
                "peer_feedback.reviewer_id",
                "peer_feedback.partner_id",
                "peer_feedback.low_id",
                "peer_feedback.high_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["worked_confirmation_id", "conversation_id", "reviewer_id", "worked_answer"],
            [
                "study_outcome_revisions.id",
                "study_outcome_revisions.conversation_id",
                "study_outcome_revisions.actor_id",
                "study_outcome_revisions.answer",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["low_message_id", "conversation_id", "low_id"],
            ["messages.id", "messages.conversation_id", "messages.author_id"],
            name="fk_peer_feedback_low_human",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["high_message_id", "conversation_id", "high_id"],
            ["messages.id", "messages.conversation_id", "messages.author_id"],
            name="fk_peer_feedback_high_human",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="positive_revision"),
        CheckConstraint("worked_answer='yes'", name="explicit_worked_yes"),
        CheckConstraint("again IN ('yes','maybe','no')", name="bounded_again"),
        CheckConstraint(
            "low_message_id IS NULL OR high_message_id IS NULL OR low_message_id != "
            "high_message_id",
            name="distinct_human_messages",
        ),
        CheckConstraint(
            "cardinality(descriptors) <= 3 AND (array_ndims(descriptors)=1 OR "
            "cardinality(descriptors)=0) AND array_position(descriptors,NULL) IS "
            "NULL AND descriptors <@ "
            "ARRAY['easy_to_communicate','prepared','supportive']::varchar[] AND "
            "cardinality(array_positions(descriptors,'easy_to_communicate'))<=1 AND "
            "cardinality(array_positions(descriptors,'prepared'))<=1 AND "
            "cardinality(array_positions(descriptors,'supportive'))<=1",
            name="bounded_unique_descriptors",
        ),
        CheckConstraint(
            "team_note IS NULL OR (length(team_note) BETWEEN 1 AND 1000 AND "
            "team_note ~ '[^[:space:]]')",
            name="bounded_team_note",
        ),
        *origin_checks(),
    )
    feedback_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column()
    reviewer_id: Mapped[UUID] = mapped_column()
    partner_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    worked_confirmation_id: Mapped[UUID] = mapped_column()
    worked_answer: Mapped[str] = mapped_column(String(20))
    low_message_id: Mapped[UUID | None] = mapped_column()
    high_message_id: Mapped[UUID | None] = mapped_column()
    again: Mapped[str] = mapped_column(String(5))
    descriptors: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    team_note: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class PeerFeedbackRemovalRecord(Base):
    __tablename__ = "peer_feedback_removals"
    __table_args__ = (
        UniqueConstraint("id", "feedback_id", name="uq_peer_feedback_removals_owned"),
        ForeignKeyConstraint(
            ["feedback_id", "source_version"],
            ["peer_feedback_revisions.feedback_id", "peer_feedback_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "source_version > 0 AND operator_access_version > 0", name="positive_source_revisions"
        ),
        CheckConstraint("operator_access_active", name="active_operator_source"),
        CheckConstraint("kind IN ('fraudulent','abusive')", name="bounded_kind"),
        CheckConstraint(
            "length(reason) BETWEEN 1 AND 1000 AND reason ~ '[^[:space:]]'", name="bounded_reason"
        ),
        *origin_checks(),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    feedback_id: Mapped[UUID] = mapped_column()
    source_version: Mapped[int] = mapped_column()
    operator_id: Mapped[UUID] = mapped_column()
    operator_access_version: Mapped[int] = mapped_column()
    operator_access_active: Mapped[bool] = mapped_column()
    kind: Mapped[str] = mapped_column(String(12))
    reason: Mapped[str] = mapped_column(Text)
    removed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class StudyPromptReceiptRecord(Base):
    __tablename__ = "study_prompt_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "conversation_id", name="uq_study_prompt_receipts_once"),
        UniqueConstraint(
            "id", "conversation_id", "actor_id", name="uq_study_prompt_receipts_event_source"
        ),
        ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "low_id < high_id AND actor_id IN (low_id,high_id)", name="participant_actor"
        ),
        *origin_checks(),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column()
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class FeedbackCommandIntentRecord(Base):
    __tablename__ = "feedback_command_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["outcome_id", "conversation_id", "actor_id"],
            [
                "study_outcome_revisions.id",
                "study_outcome_revisions.conversation_id",
                "study_outcome_revisions.actor_id",
            ],
            name="fk_feedback_intents_outcome",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["feedback_id", "feedback_version", "actor_id", "conversation_id"],
            [
                "peer_feedback_revisions.feedback_id",
                "peer_feedback_revisions.version",
                "peer_feedback_revisions.reviewer_id",
                "peer_feedback_revisions.conversation_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["prompt_id", "conversation_id", "actor_id"],
            [
                "study_prompt_receipts.id",
                "study_prompt_receipts.conversation_id",
                "study_prompt_receipts.actor_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "low_id < high_id AND actor_id IN (low_id,high_id)", name="participant_actor"
        ),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="bounded_key"),
        CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_shape"),
        CheckConstraint(
            "(operation='study_outcome' AND result_kind='outcome' AND outcome_id IS "
            "NOT NULL AND feedback_id IS NULL AND feedback_version IS NULL AND "
            "prompt_id IS NULL) OR (operation='assessment' AND "
            "result_kind='assessment' AND feedback_id IS NOT NULL AND "
            "feedback_version IS NOT NULL AND feedback_version > 0 AND outcome_id IS "
            "NULL AND prompt_id IS NULL) OR (operation='prompt_visit' AND "
            "result_kind='prompt' AND prompt_id IS NOT NULL AND outcome_id IS NULL "
            "AND feedback_id IS NULL AND feedback_version IS NULL) OR "
            "(operation='prompt_visit' AND result_kind='no_offer' AND prompt_id IS "
            "NULL AND outcome_id IS NULL AND feedback_id IS NULL AND "
            "feedback_version IS NULL)",
            name="typed_result",
        ),
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    operation: Mapped[str] = mapped_column(String(20), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    conversation_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result_kind: Mapped[str] = mapped_column(String(12))
    outcome_id: Mapped[UUID | None] = mapped_column()
    feedback_id: Mapped[UUID | None] = mapped_column()
    feedback_version: Mapped[int | None] = mapped_column()
    prompt_id: Mapped[UUID | None] = mapped_column()
