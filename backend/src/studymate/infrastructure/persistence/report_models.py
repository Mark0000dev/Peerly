"""Retained disclosure references and private, actor-owned profile reports."""

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class ProfileAccessRecord(Base):
    __tablename__ = "profile_access_contexts"
    __table_args__ = (
        UniqueConstraint("id", "viewer_id", name="uq_profile_access_contexts_viewer"),
        ForeignKeyConstraint(
            ["target_id", "profile_version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_id", "photo_version"],
            ["photo_revisions.account_id", "photo_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_id", "goal_id", "goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_id", "help_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("viewer_id != target_id", name="distinct_participants"),
        CheckConstraint("profile_version > 0 AND photo_version > 0", name="positive_versions"),
        CheckConstraint(
            "(goal_id IS NULL AND goal_version IS NULL) OR "
            "(goal_id IS NOT NULL AND goal_version IS NOT NULL AND goal_version > 0)",
            name="goal_reference_shape",
        ),
        CheckConstraint("help_version IS NULL OR help_version > 0", name="help_version"),
        CheckConstraint(
            "request_id IS NOT NULL OR "
            "(action_id IS NULL AND trace_id IS NULL AND span_id IS NULL)",
            name="origin_request",
        ),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR "
            "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
            "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0', 32) AND "
            "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))",
            name="origin_trace_pair",
        ),
        Index("ix_profile_access_contexts_viewer_issued", "viewer_id", "issued_at", "id"),
        Index("ix_profile_access_contexts_target", "target_id", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    viewer_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    target_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    profile_version: Mapped[int] = mapped_column()
    photo_version: Mapped[int] = mapped_column()
    goal_id: Mapped[UUID | None] = mapped_column()
    goal_version: Mapped[int | None] = mapped_column()
    help_version: Mapped[int | None] = mapped_column()
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class ProfileReportRecord(Base):
    __tablename__ = "profile_reports"
    __table_args__ = (
        UniqueConstraint("id", "reporter_id", name="uq_profile_reports_reporter"),
        ForeignKeyConstraint(
            ["context_id", "reporter_id"],
            ["profile_access_contexts.id", "profile_access_contexts.viewer_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["message_context_id", "reporter_id"],
            ["message_report_contexts.id", "message_report_contexts.viewer_id"],
            name="fk_reports_owned_message_context",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(kind='profile' AND context_id IS NOT NULL AND message_context_id IS NULL) OR "
            "(kind='message_image' AND context_id IS NULL AND message_context_id IS NOT NULL)",
            name="evidence_kind",
        ),
        CheckConstraint(
            "category IN ('impersonation','harassment','inappropriate_content','spam','other')",
            name="known_category",
        ),
        CheckConstraint(
            "comment IS NULL OR length(comment) BETWEEN 1 AND 1000", name="comment_length"
        ),
        CheckConstraint("category != 'other' OR comment IS NOT NULL", name="other_explanation"),
        Index("ix_profile_reports_reporter_submitted", "reporter_id", "submitted_at", "id"),
        Index("ix_profile_reports_submitted", "submitted_at", "id"),
        Index("ix_profile_reports_context_submitted", "context_id", "submitted_at", "id"),
        Index(
            "ix_profile_reports_message_context_submitted",
            "message_context_id",
            "submitted_at",
            "id",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    reporter_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(16), server_default="profile")
    context_id: Mapped[UUID | None] = mapped_column()
    message_context_id: Mapped[UUID | None] = mapped_column()
    category: Mapped[str] = mapped_column(String(24))
    comment: Mapped[str | None] = mapped_column(String(1000))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProfileReportIntentRecord(Base):
    __tablename__ = "profile_report_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["report_id", "reporter_id"],
            ["profile_reports.id", "profile_reports.reporter_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        CheckConstraint("octet_length(fingerprint) = 32", name="fingerprint_length"),
    )
    reporter_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    report_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
