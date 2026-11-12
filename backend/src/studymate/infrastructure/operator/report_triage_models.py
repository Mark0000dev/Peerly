"""Actual immutable triage evidence and enqueue provenance; main owns0060 DDL/registry."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class ReportTriageEvidenceRecord(Base):
    __tablename__ = "report_triage_evidence_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "version",
            "operator_id",
            "operator_access_version",
            "operator_access_active",
            "actor_session_id",
            name="uq_triage_snapshot_actor_source",
        ),
        ForeignKeyConstraint(
            ["report_id", "previous_version"],
            [
                "report_triage_evidence_snapshots.report_id",
                "report_triage_evidence_snapshots.version",
            ],
            name="fk_triage_snapshot_previous",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_id", "review_version"],
            [
                "operator_report_review_revisions.report_id",
                "operator_report_review_revisions.version",
            ],
            name="fk_triage_snapshot_review",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            name="fk_triage_snapshot_grant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["actor_session_id", "operator_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_triage_snapshot_session",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_id", "report_kind", "reporter_id"],
            ["profile_reports.id", "profile_reports.kind", "profile_reports.reporter_id"],
            name="fk_triage_snapshot_report_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_id", "profile_context_id"],
            ["profile_reports.id", "profile_reports.context_id"],
            name="fk_triage_snapshot_report_profile",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_id", "message_context_id"],
            ["profile_reports.id", "profile_reports.message_context_id"],
            name="fk_triage_snapshot_report_message",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["profile_context_id", "reporter_id", "target_id"],
            [
                "profile_access_contexts.id",
                "profile_access_contexts.viewer_id",
                "profile_access_contexts.target_id",
            ],
            name="fk_triage_snapshot_profile_evidence",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["message_context_id", "reporter_id", "target_id"],
            [
                "message_report_contexts.id",
                "message_report_contexts.viewer_id",
                "message_report_contexts.target_id",
            ],
            name="fk_triage_snapshot_message_evidence",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(report_kind='profile' AND profile_context_id IS NOT NULL "
            "AND message_context_id IS NULL) OR "
            "(report_kind='message_image' AND profile_context_id IS NULL "
            "AND message_context_id IS NOT NULL)",
            name="actual_evidence_kind",
        ),
        CheckConstraint(
            "version>0 AND ((version=1 AND previous_version IS NULL) OR "
            "(previous_version IS NOT NULL AND previous_version>0 "
            "AND version=previous_version+1))",
            name="consecutive_versions",
        ),
        CheckConstraint("review_version IS NULL OR review_version>0", name="actual_review_version"),
        CheckConstraint(
            "operator_access_active=true AND operator_access_version>0",
            name="original_active_grant",
        ),
        CheckConstraint(
            "length(evidence) BETWEEN 1 AND 4000 AND length(btrim(evidence))>0",
            name="bounded_actual_evidence",
        ),
        CheckConstraint("octet_length(evidence_digest)=32", name="evidence_digest_length"),
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("profile_reports.id", ondelete="RESTRICT"), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    report_kind: Mapped[str] = mapped_column(String(16))
    reporter_id: Mapped[UUID] = mapped_column()
    target_id: Mapped[UUID] = mapped_column()
    profile_context_id: Mapped[UUID | None] = mapped_column()
    message_context_id: Mapped[UUID | None] = mapped_column()
    previous_version: Mapped[int | None] = mapped_column()
    review_version: Mapped[int | None] = mapped_column()
    operator_id: Mapped[UUID] = mapped_column()
    operator_access_version: Mapped[int] = mapped_column()
    operator_access_active: Mapped[bool] = mapped_column()
    actor_session_id: Mapped[UUID] = mapped_column()
    evidence: Mapped[str] = mapped_column(Text)
    evidence_digest: Mapped[bytes] = mapped_column(LargeBinary(32))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportTriageSubmissionRecord(Base):
    __tablename__ = "report_triage_submissions"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_triage_submission_event"),
        UniqueConstraint(
            "job_id",
            "report_id",
            "source_version",
            "operator_id",
            name="uq_triage_submission_canonical",
        ),
        ForeignKeyConstraint(
            [
                "report_id",
                "source_version",
                "operator_id",
                "operator_access_version",
                "operator_access_active",
                "actor_session_id",
            ],
            [
                "report_triage_evidence_snapshots.report_id",
                "report_triage_evidence_snapshots.version",
                "report_triage_evidence_snapshots.operator_id",
                "report_triage_evidence_snapshots.operator_access_version",
                "report_triage_evidence_snapshots.operator_access_active",
                "report_triage_evidence_snapshots.actor_session_id",
            ],
            name="fk_triage_submission_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["job_id", "operator_id", "kind", "report_id", "source_version"],
            [
                "ai_jobs.id",
                "ai_jobs.actor_id",
                "ai_jobs.kind",
                "ai_jobs.source_id",
                "ai_jobs.source_version",
            ],
            name="fk_triage_submission_job",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["event_id", "operator_id", "event_kind", "submitted_at"],
            [
                "product_events.id",
                "product_events.account_id",
                "product_events.kind",
                "product_events.occurred_at",
            ],
            name="fk_triage_submission_event",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "kind='triage_report' AND event_kind='triage.submitted'",
            name="actual_internal_submission",
        ),
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
    job_id: Mapped[UUID] = mapped_column(primary_key=True)
    report_id: Mapped[UUID] = mapped_column()
    source_version: Mapped[int] = mapped_column()
    operator_id: Mapped[UUID] = mapped_column()
    operator_access_version: Mapped[int] = mapped_column()
    operator_access_active: Mapped[bool] = mapped_column()
    actor_session_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(24))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_id: Mapped[UUID] = mapped_column()
    event_kind: Mapped[str] = mapped_column(String(32))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
