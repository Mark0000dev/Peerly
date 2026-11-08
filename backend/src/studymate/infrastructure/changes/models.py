"""Transport-only committed sources; no copied private business payloads."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class ChangeHeadRecord(Base):
    __tablename__ = "change_recipient_heads"
    __table_args__ = (
        CheckConstraint("next_sequence > 0", name="positive_next_sequence"),
        CheckConstraint(
            "expired_through_sequence >= 0 AND expired_through_sequence < next_sequence",
            name="retained_floor",
        ),
    )
    recipient_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    next_sequence: Mapped[int] = mapped_column(BigInteger)
    expired_through_sequence: Mapped[int] = mapped_column(BigInteger)


class ChangeOutboxRecord(Base):
    __tablename__ = "change_outbox"
    __table_args__ = (
        UniqueConstraint(
            "recipient_id", "published_sequence", name="uq_change_outbox_recipient_sequence"
        ),
        CheckConstraint(
            "(published_sequence IS NULL AND published_at IS NULL) OR "
            "(published_sequence IS NOT NULL AND published_sequence > 0 "
            "AND published_at IS NOT NULL)",
            name="paired_publication",
        ),
        Index(
            "ix_change_outbox_due",
            "staged_at",
            "canonical_event_id",
            "recipient_id",
            postgresql_where=text("published_sequence IS NULL"),
        ),
    )
    canonical_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_events.id", ondelete="RESTRICT"), primary_key=True
    )
    recipient_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    staged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_sequence: Mapped[int | None] = mapped_column(BigInteger)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublishedChangeRecord(Base):
    __tablename__ = "published_changes"
    __table_args__ = (
        UniqueConstraint(
            "canonical_event_id", "recipient_id", name="uq_published_changes_source_recipient"
        ),
        ForeignKeyConstraint(
            ["canonical_event_id", "recipient_id"],
            ["change_outbox.canonical_event_id", "change_outbox.recipient_id"],
            name="fk_published_changes_actual_staged_source",
            ondelete="RESTRICT",
        ),
        CheckConstraint("sequence > 0", name="positive_sequence"),
        Index("ix_published_changes_retention", "published_at", "recipient_id", "sequence"),
    )
    recipient_id: Mapped[UUID] = mapped_column(
        ForeignKey("change_recipient_heads.recipient_id", ondelete="RESTRICT"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    canonical_event_id: Mapped[UUID] = mapped_column()
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
