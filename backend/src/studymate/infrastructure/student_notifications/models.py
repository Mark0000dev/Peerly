from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class ConsumerRecord(Base):
    __tablename__ = "student_notification_consumers"
    __table_args__ = (CheckConstraint("name = 'student_push_v1'", name="known_consumer"),)
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeliveryRecord(Base):
    __tablename__ = "student_notification_deliveries"
    __table_args__ = (
        UniqueConstraint("id", "recipient_id", name="uq_student_notification_owned_delivery"),
        UniqueConstraint(
            "event_id", "recipient_id", name="uq_student_notification_event_recipient"
        ),
        CheckConstraint("kind IN ('message','request','accepted_connection')", name="known_kind"),
        CheckConstraint(
            "state IN ('pending','claimed','sending','delivered','cancelled','rejected','unknown')",
            name="known_state",
        ),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="bounded_attempts"),
        CheckConstraint("actor_id <> recipient_id", name="different_actor_recipient"),
        CheckConstraint(
            "expires_at > created_at AND due_at >= created_at", name="valid_delivery_times"
        ),
        CheckConstraint(
            "((state IN ('claimed','sending')) AND lease_token IS NOT NULL "
            "AND lease_until IS NOT NULL) OR ((state NOT IN ('claimed','sending')) "
            "AND lease_token IS NULL AND lease_until IS NULL)",
            name="lease_shape",
        ),
        Index("ix_student_notifications_due", "state", "due_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("product_events.id", ondelete="RESTRICT"))
    recipient_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    relationship_id: Mapped[UUID] = mapped_column(
        ForeignKey("relationships.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(24))
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int]
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
