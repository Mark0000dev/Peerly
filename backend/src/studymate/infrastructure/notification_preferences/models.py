from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class PreferenceRevisionRecord(Base):
    __tablename__ = "notification_preference_revisions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="positive_version"),
        CheckConstraint("mode IN ('messages_and_requests', 'all_updates')", name="known_mode"),
    )
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(32))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PreferenceIntentRecord(Base):
    __tablename__ = "notification_preference_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "result_version"],
            [
                "notification_preference_revisions.account_id",
                "notification_preference_revisions.version",
            ],
        ),
        CheckConstraint("octet_length(fingerprint) = 32", name="fingerprint_length"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="valid_key"),
    )
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    result_version: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
