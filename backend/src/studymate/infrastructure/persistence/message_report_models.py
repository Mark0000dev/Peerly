"""Retained participant-owned evidence for reporting an actual confirmed image."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class MessageReportContextRecord(Base):
    __tablename__ = "message_report_contexts"
    __table_args__ = (
        UniqueConstraint("id", "viewer_id", name="uq_message_report_context_owner"),
        ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "message_id",
                "conversation_id",
                "target_id",
                "client_message_id",
                "image_id",
                "image_version",
                "image_attempt_id",
                "image_state",
            ],
            [
                "messages.id",
                "messages.conversation_id",
                "messages.author_id",
                "messages.client_message_id",
                "messages.image_id",
                "messages.image_version",
                "messages.image_attempt_id",
                "messages.image_state",
            ],
            name="fk_message_report_actual_image",
            ondelete="RESTRICT",
        ),
        CheckConstraint("low_id < high_id", name="canonical_pair"),
        CheckConstraint("viewer_id IN (low_id, high_id)", name="participant_reporter"),
        CheckConstraint(
            "target_id IN (low_id, high_id) AND viewer_id != target_id", name="peer_author"
        ),
        CheckConstraint("image_version > 0 AND image_state='ready'", name="ready_source"),
        CheckConstraint(
            "request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL "
            "AND span_id IS NULL)",
            name="origin_request",
        ),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND "
            "span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != "
            "repeat('0', 32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != "
            "repeat('0', 16))",
            name="origin_trace_pair",
        ),
        Index("ix_message_report_contexts_viewer_issued", "viewer_id", "issued_at", "id"),
        Index("ix_message_report_contexts_message_issued", "message_id", "issued_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    viewer_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    message_id: Mapped[UUID] = mapped_column()
    conversation_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    target_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    client_message_id: Mapped[UUID] = mapped_column()
    image_id: Mapped[UUID] = mapped_column()
    image_version: Mapped[int] = mapped_column()
    image_attempt_id: Mapped[UUID] = mapped_column()
    image_state: Mapped[str] = mapped_column(String(16))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
