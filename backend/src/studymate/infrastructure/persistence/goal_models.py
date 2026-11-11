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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class GoalRecord(Base):
    __tablename__ = "goals"
    __table_args__ = (
        UniqueConstraint("id", "account_id", name="uq_goals_id_account"),
        ForeignKeyConstraint(
            ["id", "current_version"],
            ["goal_revisions.goal_id", "goal_revisions.version"],
            name="fk_goals_current_revision",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint("current_version > 0", name="positive_version"),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at", name="valid_completion"
        ),
        Index(
            "uq_goals_active_account",
            "account_id",
            unique=True,
            postgresql_where=text("completed_at IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    current_version: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GoalRevisionRecord(Base):
    __tablename__ = "goal_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["goal_id", "account_id"], ["goals.id", "goals.account_id"], ondelete="RESTRICT"
        ),
        UniqueConstraint(
            "account_id", "goal_id", "version", name="uq_goal_revisions_owner_version"
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("length(subject_label) BETWEEN 1 AND 80", name="subject_label_length"),
        CheckConstraint("topic IS NULL OR length(topic) BETWEEN 1 AND 80", name="topic_length"),
        CheckConstraint(
            "(topic IS NULL AND topic_match_key IS NULL) OR "
            "(topic IS NOT NULL AND topic_match_key IS NOT NULL AND length(topic_match_key) > 0)",
            name="topic_key_shape",
        ),
        Index(
            "ix_goal_revisions_subject_topic", "subject_id", "topic_match_key", "goal_id", "version"
        ),
        CheckConstraint(
            "context IS NULL OR length(context) BETWEEN 1 AND 240", name="context_length"
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at = saved_at", name="final_revision_time"
        ),
    )
    goal_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column()
    subject_id: Mapped[UUID | None] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"))
    subject_label: Mapped[str] = mapped_column(String(80))
    topic: Mapped[str | None] = mapped_column(String(80))
    topic_match_key: Mapped[str | None] = mapped_column(String(240))
    context: Mapped[str | None] = mapped_column(String(240))
    shared_learning: Mapped[bool] = mapped_column()
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GoalIntentRecord(Base):
    __tablename__ = "goal_write_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "goal_id", "result_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
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
    goal_id: Mapped[UUID] = mapped_column()
    result_version: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
