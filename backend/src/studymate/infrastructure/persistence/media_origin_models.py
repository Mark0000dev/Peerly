from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class MediaOriginRecord(Base):
    __tablename__ = "media_execution_origins"
    __table_args__ = (
        CheckConstraint("phase IN ('created', 'queued')", name="known_phase"),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR "
            "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
            "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0', 32) AND "
            "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))",
            name="origin_trace_pair",
        ),
    )
    upload_id: Mapped[UUID] = mapped_column(
        ForeignKey("photo_uploads.id", ondelete="RESTRICT"), primary_key=True
    )
    phase: Mapped[str] = mapped_column(String(16), primary_key=True)
    request_id: Mapped[UUID] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
