from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class HelpRevisionRecord(Base):
    __tablename__ = "help_revisions"
    __table_args__ = (CheckConstraint("version > 0", name="positive_version"),)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HelpRecord(Base):
    __tablename__ = "help_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "current_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("current_version > 0", name="positive_version"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    current_version: Mapped[int] = mapped_column()


class HelpSelectionRecord(Base):
    __tablename__ = "help_selections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "version"],
            ["help_revisions.account_id", "help_revisions.version"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("account_id", "version", "subject_id", name="uq_help_selections_subject"),
        CheckConstraint("slot BETWEEN 0 AND 4", name="bounded_slot"),
        CheckConstraint("length(subject_label) BETWEEN 1 AND 80", name="subject_label_length"),
        CheckConstraint(
            "topic_note IS NULL OR length(topic_note) BETWEEN 1 AND 80", name="topic_note_length"
        ),
        CheckConstraint(
            "(topic_note IS NULL AND topic_match_key IS NULL) OR "
            "(topic_note IS NOT NULL AND topic_match_key IS NOT NULL "
            "AND length(topic_match_key) > 0)",
            name="topic_key_shape",
        ),
        Index(
            "ix_help_selections_subject_topic",
            "subject_id",
            "topic_match_key",
            "account_id",
            "version",
        ),
    )
    account_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    slot: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"))
    subject_label: Mapped[str] = mapped_column(String(80))
    topic_note: Mapped[str | None] = mapped_column(String(80))
    topic_match_key: Mapped[str | None] = mapped_column(String(240))


class HelpIntentRecord(Base):
    __tablename__ = "help_write_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "result_version"],
            ["help_revisions.account_id", "help_revisions.version"],
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
