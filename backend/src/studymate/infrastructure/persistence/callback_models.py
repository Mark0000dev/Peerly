"""Nonsecret callback attempt metadata; no callback URL, code or browser token."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class CallbackAttemptRecord(Base):
    __tablename__ = "login_callback_attempts"
    __table_args__ = (
        CheckConstraint("octet_length(source_digest) = 32", name="source_digest_length"),
        CheckConstraint(
            "succeeded_at IS NULL OR succeeded_at >= started_at", name="valid_success_time"
        ),
        CheckConstraint(
            "(succeeded_at IS NULL) = (account_id IS NULL)", name="success_identifies_account"
        ),
        Index("ix_login_callback_attempts_source_time", "source_digest", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_digest: Mapped[bytes] = mapped_column(LargeBinary)
    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
