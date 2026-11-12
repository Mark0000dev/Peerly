"""Retained human photo sources with0059 source/canonical integrity constraints."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class OperatorPhotoReviewRecord(Base):
    __tablename__ = "operator_photo_review_revisions"
    __table_args__ = (
        UniqueConstraint("account_id", "version", name="uq_photo_review_version"),
        UniqueConstraint("id", "account_id", "version", name="uq_photo_review_lineage"),
        UniqueConstraint("id", "operator_id", name="uq_photo_review_actor_source"),
        UniqueConstraint(
            "id", "version", "operator_id", "action", name="uq_photo_review_canonical_source"
        ),
        ForeignKeyConstraint(
            ["account_id", "photo_version"],
            ["photo_revisions.account_id", "photo_revisions.version"],
            ondelete="RESTRICT",
            name="fk_photo_review_publication",
        ),
        ForeignKeyConstraint(
            ["previous_revision_id", "account_id", "previous_version"],
            [
                "operator_photo_review_revisions.id",
                "operator_photo_review_revisions.account_id",
                "operator_photo_review_revisions.version",
            ],
            ondelete="RESTRICT",
            name="fk_photo_review_previous",
        ),
        ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            ondelete="RESTRICT",
            name="fk_photo_review_grant",
        ),
        ForeignKeyConstraint(
            ["session_id", "operator_id"],
            ["sessions.id", "sessions.account_id"],
            ondelete="RESTRICT",
            name="fk_photo_review_session",
        ),
        ForeignKeyConstraint(
            ["id", "operator_id", "event_kind", "decided_at"],
            [
                "product_events.id",
                "product_events.account_id",
                "product_events.kind",
                "product_events.occurred_at",
            ],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            name="fk_photo_review_event",
        ),
        CheckConstraint("version>0 AND photo_version>0", name="positive_versions"),
        CheckConstraint(
            "(version=1 AND previous_version IS NULL AND previous_revision_id IS NULL "
            "AND action='require_replacement') OR "
            "(version>1 AND previous_version IS NOT NULL AND previous_version=version-1 "
            "AND previous_revision_id IS NOT NULL)",
            name="ordered_lineage",
        ),
        CheckConstraint(
            "action IN ('require_replacement','approve_replacement')", name="human_action"
        ),
        CheckConstraint(
            "operator_access_active=true AND operator_access_version>0", name="actual_active_grant"
        ),
        CheckConstraint("event_kind='photo.reviewed'", name="actual_photo_review_event"),
        CheckConstraint(
            "char_length(reason) BETWEEN 1 AND 1000 AND btrim(reason)<>''", name="bounded_reason"
        ),
        CheckConstraint(
            "http_request_id IS NOT NULL OR "
            "(action_id IS NULL AND trace_id IS NULL AND span_id IS NULL)",
            name="origin_requires_request",
        ),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR "
            "(trace_id IS NOT NULL AND span_id IS NOT NULL "
            "AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id<>'00000000000000000000000000000000' "
            "AND span_id ~ '^[0-9a-f]{16}$' AND span_id<>'0000000000000000')",
            name="paired_trace",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column()
    previous_revision_id: Mapped[UUID | None] = mapped_column()
    previous_version: Mapped[int | None] = mapped_column()
    action: Mapped[str] = mapped_column(String(32))
    photo_version: Mapped[int] = mapped_column()
    operator_id: Mapped[UUID] = mapped_column()
    operator_access_version: Mapped[int] = mapped_column()
    operator_access_active: Mapped[bool] = mapped_column()
    session_id: Mapped[UUID] = mapped_column()
    event_kind: Mapped[str] = mapped_column(String(32))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(1000))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class OperatorPhotoReviewIntentRecord(Base):
    __tablename__ = "operator_photo_review_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "operator_id"],
            ["operator_photo_review_revisions.id", "operator_photo_review_revisions.operator_id"],
            ondelete="RESTRICT",
            name="fk_photo_review_intent_source",
        ),
        UniqueConstraint("revision_id", name="uq_photo_review_intent_source"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="valid_key"),
        CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_length"),
    )
    operator_id: Mapped[UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
