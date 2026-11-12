"""Owned report-review proof models; main owns migration59 and metadata registration."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class ReportReviewRevisionRecord(Base):
    __tablename__ = "operator_report_review_revisions"
    __table_args__ = (
        UniqueConstraint("report_id", "version", name="uq_report_review_version"),
        UniqueConstraint("id", "operator_id", name="uq_report_review_actor_source"),
        UniqueConstraint(
            "id",
            "report_id",
            "version",
            "operator_id",
            "action",
            name="uq_report_review_canonical_source",
        ),
        UniqueConstraint("event_id", name="uq_report_review_event"),
        ForeignKeyConstraint(
            ["report_id", "previous_version"],
            [
                "operator_report_review_revisions.report_id",
                "operator_report_review_revisions.version",
            ],
            name="fk_report_review_previous",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            name="fk_report_review_grant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actor_session_id", "operator_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_report_review_session",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["event_id", "operator_id", "event_kind", "reviewed_at"],
            [
                "product_events.id",
                "product_events.account_id",
                "product_events.kind",
                "product_events.occurred_at",
            ],
            name="fk_report_review_event",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "version>0 AND ((version=1 AND previous_version IS NULL) OR "
            "(previous_version IS NOT NULL AND previous_version>0 AND version=previous_version+1))",
            name="consecutive_versions",
        ),
        CheckConstraint("action IN ('dismiss','escalate')", name="human_action"),
        CheckConstraint(
            "length(reason) BETWEEN 1 AND 1000 AND length(btrim(reason))>0",
            name="documented_reason",
        ),
        CheckConstraint(
            "operator_access_active=true AND operator_access_version>0",
            name="active_original_grant",
        ),
        CheckConstraint("event_kind='report.reviewed'", name="actual_review_event"),
        CheckConstraint(
            "http_request_id IS NOT NULL OR "
            "(action_id IS NULL AND trace_id IS NULL AND span_id IS NULL)",
            name="origin_request",
        ),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR "
            "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
            "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0',32) AND "
            "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0',16))",
            name="origin_trace_pair",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    report_id: Mapped[UUID] = mapped_column(ForeignKey("profile_reports.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column()
    previous_version: Mapped[int | None] = mapped_column()
    action: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(1000))
    operator_id: Mapped[UUID] = mapped_column()
    operator_access_version: Mapped[int] = mapped_column()
    operator_access_active: Mapped[bool] = mapped_column()
    actor_session_id: Mapped[UUID] = mapped_column()
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_id: Mapped[UUID] = mapped_column()
    event_kind: Mapped[str] = mapped_column(String(32))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class ReportReviewIntentRecord(Base):
    __tablename__ = "operator_report_review_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["review_id", "operator_id"],
            ["operator_report_review_revisions.id", "operator_report_review_revisions.operator_id"],
            name="fk_report_review_intent_source",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("review_id", name="uq_report_review_intent_source"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="valid_key"),
        CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_length"),
    )
    operator_id: Mapped[UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    review_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
