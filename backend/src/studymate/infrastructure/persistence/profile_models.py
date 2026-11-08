"""Immutable saved revisions and current pointer; no premature photo/publication state."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    UniqueConstraint,
    column,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.domain.language_data import LANGUAGE_CHOICES
from studymate.infrastructure.persistence.base import Base


class ProfileRevisionRecord(Base):
    __tablename__ = "profile_revisions"
    __table_args__ = (
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "display_name IS NULL OR length(display_name) BETWEEN 2 AND 50",
            name="display_name_length",
        ),
        CheckConstraint("about IS NULL OR length(about) BETWEEN 1 AND 160", name="about_length"),
        CheckConstraint(
            "programme IS NULL OR length(programme) BETWEEN 1 AND 80", name="programme_length"
        ),
        CheckConstraint(
            "year_label IS NULL OR length(year_label) BETWEEN 1 AND 32", name="year_label_length"
        ),
        CheckConstraint("task IN ('find_help', 'offer_help')", name="known_task"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(50))
    about: Mapped[str | None] = mapped_column(String(160))
    programme: Mapped[str | None] = mapped_column(String(80))
    year_label: Mapped[str | None] = mapped_column(String(32))
    task: Mapped[str] = mapped_column(String(16))
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProfileRecord(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "current_version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("current_version > 0", name="positive_version"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    current_version: Mapped[int] = mapped_column()


class ProfileLanguageRecord(Base):
    __tablename__ = "profile_languages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("account_id", "version", "code", name="uq_profile_languages_selection"),
        CheckConstraint("slot BETWEEN 0 AND 4", name="bounded_slot"),
        CheckConstraint(
            column("code").in_(tuple(code for code, _label in LANGUAGE_CHOICES)),
            name="known_selection",
        ),
        CheckConstraint("code ~ '^[a-z]{2,3}(-[a-z0-9]{2,8})*$'", name="selection_shape"),
    )
    account_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    slot: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(35))


class ProfileIntentRecord(Base):
    __tablename__ = "profile_write_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "result_version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        CheckConstraint("octet_length(fingerprint) = 32", name="fingerprint_length"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    result_version: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
