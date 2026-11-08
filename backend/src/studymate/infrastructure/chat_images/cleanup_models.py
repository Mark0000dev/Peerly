"""Transport-only cleanup metadata; originals and display renditions are never targets."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class ChatImageTransportCleanupRecord(Base):
    __tablename__ = "chat_image_transport_cleanup"
    __table_args__ = (
        CheckConstraint("attempts>=0", name="nonnegative_attempts"),
        CheckConstraint("(generation IS NULL)=(lease_until IS NULL)", name="paired_lease"),
        CheckConstraint(
            "cleaned_at IS NULL OR lease_until IS NULL", name="finished_lease_released"
        ),
        Index(
            "ix_chat_image_transport_cleanup_pending",
            "next_attempt_at",
            "image_id",
            postgresql_where=text("cleaned_at IS NULL"),
        ),
    )
    image_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "chat_image_preparations.id",
            name="fk_chat_image_cleanup_owned_source",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    attempts: Mapped[int] = mapped_column()
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generation: Mapped[UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
