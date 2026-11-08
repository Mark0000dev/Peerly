"""UNREGISTERED until owner migration0030 alignment; retained technical sources/ACKs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class RequestDisclosureRecord(Base):
    __tablename__ = "request_disclosures"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "viewer_id",
            "request_id",
            "stored_version",
            name="uq_request_disclosures_owned_source",
        ),
        ForeignKeyConstraint(
            ["request_id", "sender_id", "recipient_id"],
            [
                "connection_requests.id",
                "connection_requests.sender_id",
                "connection_requests.recipient_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["request_id", "stored_version"],
            ["request_revisions.request_id", "request_revisions.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("viewer_id IN (sender_id, recipient_id)", name="participant_viewer"),
        CheckConstraint("stored_version > 0", name="positive_stored_version"),
        Index("ix_request_disclosures_viewer_request", "viewer_id", "request_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    viewer_id: Mapped[UUID] = mapped_column()
    request_id: Mapped[UUID] = mapped_column()
    stored_version: Mapped[int] = mapped_column()
    sender_id: Mapped[UUID] = mapped_column()
    recipient_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class RequestViewAcknowledgementRecord(Base):
    __tablename__ = "request_view_acknowledgements"
    __table_args__ = (
        UniqueConstraint(
            "viewer_id", "request_id", "stored_version", name="uq_request_view_ack_source"
        ),
        UniqueConstraint("id", "viewer_id", name="uq_request_view_ack_owner"),
        UniqueConstraint(
            "id",
            "viewer_id",
            "request_id",
            "stored_version",
            name="uq_request_view_ack_owned_source",
        ),
        ForeignKeyConstraint(
            ["disclosure_id", "viewer_id", "request_id", "stored_version"],
            [
                "request_disclosures.id",
                "request_disclosures.viewer_id",
                "request_disclosures.request_id",
                "request_disclosures.stored_version",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("stored_version > 0", name="positive_stored_version"),
        Index("ix_request_view_ack_viewer_request", "viewer_id", "request_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    viewer_id: Mapped[UUID] = mapped_column()
    request_id: Mapped[UUID] = mapped_column()
    stored_version: Mapped[int] = mapped_column()
    disclosure_id: Mapped[UUID] = mapped_column()
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
