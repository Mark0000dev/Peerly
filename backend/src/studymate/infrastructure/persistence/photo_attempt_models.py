from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class PhotoAttemptRecord(Base):
    __tablename__ = "photo_processing_attempts"
    __table_args__ = (
        UniqueConstraint("upload_id", "number", name="uq_photo_processing_attempts_number"),
        UniqueConstraint("upload_id", "id", name="uq_photo_processing_attempts_upload_id"),
        CheckConstraint("number BETWEEN 1 AND 3", name="bounded_number"),
        CheckConstraint("lease_until > started_at", name="ordered_lease"),
        CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="ordered_finish"),
        CheckConstraint(
            "outcome IN ('processing', 'ready', 'retry', 'rejected', 'stale', 'interrupted')",
            name="known_outcome",
        ),
        CheckConstraint("(outcome = 'processing') = (finished_at IS NULL)", name="finish_required"),
        CheckConstraint(
            "(outcome = 'retry') = (next_attempt_at IS NOT NULL)", name="retry_required"
        ),
        CheckConstraint(
            "next_attempt_at IS NULL OR next_attempt_at > finished_at", name="ordered_retry"
        ),
        CheckConstraint(
            "failure IS NULL OR failure IN ('invalid_image', 'unsupported_format', 'too_large', "
            "'dimensions_exceeded', 'animated_image', 'content_changed', 'photo_changed', "
            "'account_unavailable', 'storage_unavailable', 'processing_unavailable')",
            name="known_failure",
        ),
        CheckConstraint(
            "(display_size IS NULL AND display_width IS NULL "
            "AND display_height IS NULL AND display_digest IS NULL) "
            "OR (display_size IS NOT NULL AND display_width IS NOT NULL "
            "AND display_height IS NOT NULL AND display_digest IS NOT NULL "
            "AND display_size > 0 AND display_width BETWEEN 1 AND 1024 "
            "AND display_height BETWEEN 1 AND 1024 AND octet_length(display_digest) = 32)",
            name="complete_display_metadata",
        ),
        CheckConstraint("outcome <> 'ready' OR display_digest IS NOT NULL", name="ready_metadata"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    upload_id: Mapped[UUID] = mapped_column(ForeignKey("photo_uploads.id", ondelete="RESTRICT"))
    number: Mapped[int] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(16))
    failure: Mapped[str | None] = mapped_column(String(32))
    display_width: Mapped[int | None] = mapped_column()
    display_height: Mapped[int | None] = mapped_column()
    display_size: Mapped[int | None] = mapped_column()
    display_digest: Mapped[bytes | None] = mapped_column(LargeBinary)
