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
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class ProfileActivationRecord(Base):
    __tablename__ = "profile_activations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "registration_id"],
            ["registration_receipts.account_id", "registration_receipts.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "profile_version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "photo_version"],
            ["photo_revisions.account_id", "photo_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "goal_id", "goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "help_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "visibility_version"],
            ["visibility_revisions.account_id", "visibility_revisions.version"],
            name="fk_profile_activations_visibility",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "profile_version > 0 AND photo_version > 0 AND visibility_version > 0",
            name="positive_versions",
        ),
        CheckConstraint(
            "(goal_id IS NULL AND goal_version IS NULL) OR "
            "(goal_id IS NOT NULL AND goal_version IS NOT NULL AND goal_version > 0)",
            name="paired_goal_revision",
        ),
        CheckConstraint("help_version IS NULL OR help_version > 0", name="positive_help_version"),
        CheckConstraint("goal_id IS NOT NULL OR help_version IS NOT NULL", name="study_context"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.account_id", ondelete="RESTRICT"), primary_key=True
    )
    registration_id: Mapped[UUID] = mapped_column()
    profile_version: Mapped[int] = mapped_column()
    photo_version: Mapped[int] = mapped_column()
    goal_id: Mapped[UUID | None] = mapped_column()
    goal_version: Mapped[int | None] = mapped_column()
    help_version: Mapped[int | None] = mapped_column()
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    visibility_version: Mapped[int] = mapped_column()


class VisibilityRevisionRecord(Base):
    __tablename__ = "visibility_revisions"
    __table_args__ = (
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("changed_at >= completed_at", name="after_completion"),
        CheckConstraint(
            "hidden_at IS NULL OR (hidden_at >= completed_at AND hidden_at <= changed_at)",
            name="ordered_hidden_time",
        ),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("profile_activations.account_id", ondelete="RESTRICT"), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VisibilityIntentRecord(Base):
    __tablename__ = "visibility_write_intents"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "key",
            "confirmed_exposure_at",
            name="uq_visibility_intents_exposure_confirmation",
        ),
        CheckConstraint(
            "(confirmed_exposure_at IS NULL AND previous_exposure_paused_at IS NULL) OR "
            "(confirmed_exposure_at IS NOT NULL AND previous_exposure_paused_at IS NOT NULL AND "
            "confirmed_exposure_at >= previous_exposure_paused_at)",
            name="exposure_confirmation",
        ),
        ForeignKeyConstraint(
            ["account_id", "result_version"],
            ["visibility_revisions.account_id", "visibility_revisions.version"],
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

    confirmed_exposure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_exposure_paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
