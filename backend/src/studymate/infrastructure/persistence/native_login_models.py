"""0061 schema metadata only; no native-login API or use cases are mounted."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class NativeAttemptRecord(Base):
    __tablename__ = "native_login_attempts"
    __table_args__ = (
        CheckConstraint("length(challenge) = 43", name="native_challenge_length"),
        CheckConstraint("octet_length(browser_digest) = 32", name="native_browser_digest_length"),
        CheckConstraint("expires_at > created_at", name="native_expiry"),
        CheckConstraint(
            "consumed_at IS NULL OR (source_digest IS NOT NULL AND consumed_at >= created_at)",
            name="native_consumption",
        ),
        CheckConstraint(
            "cancelled_at IS NULL OR (consumed_at IS NULL AND cancelled_at >= created_at)",
            name="native_cancellation",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    challenge: Mapped[str] = mapped_column(String(43))
    browser_digest: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_digest: Mapped[bytes | None] = mapped_column(
        ForeignKey("sessions.secret_digest", ondelete="RESTRICT"), unique=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
