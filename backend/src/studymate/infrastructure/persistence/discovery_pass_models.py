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


class DiscoveryContextRecord(Base):
    __tablename__ = "discovery_contexts"
    __table_args__ = (
        UniqueConstraint("id", "account_id", name="uq_discovery_context_owner"),
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
        CheckConstraint(
            "(mode IN ('find_help', 'study_together') AND goal_id IS NOT NULL "
            "AND goal_version IS NOT NULL AND goal_version > 0 AND help_version IS NULL) OR "
            "(mode = 'offer_help' AND goal_id IS NULL AND goal_version IS NULL "
            "AND help_version IS NOT NULL AND help_version > 0)",
            name="saved_source_shape",
        ),
        Index(
            "uq_discovery_context_goal",
            "account_id",
            "mode",
            "goal_id",
            "goal_version",
            unique=True,
            postgresql_where=text("goal_id IS NOT NULL"),
        ),
        Index(
            "uq_discovery_context_help",
            "account_id",
            "mode",
            "help_version",
            unique=True,
            postgresql_where=text("help_version IS NOT NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    mode: Mapped[str] = mapped_column(String(20))
    goal_id: Mapped[UUID | None] = mapped_column()
    goal_version: Mapped[int | None] = mapped_column()
    help_version: Mapped[int | None] = mapped_column()


class DiscoveryDecisionHeadRecord(Base):
    __tablename__ = "discovery_decision_heads"
    __table_args__ = (CheckConstraint("last_sequence >= 0", name="nonnegative_sequence"),)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    last_sequence: Mapped[int] = mapped_column()


class PrivatePassRecord(Base):
    __tablename__ = "private_passes"
    __table_args__ = (
        UniqueConstraint("context_id", "target_id", name="uq_private_pass_context_target"),
        UniqueConstraint("id", "account_id", name="uq_private_pass_owner"),
        UniqueConstraint("id", "context_id", "target_id", name="uq_private_pass_scope"),
        ForeignKeyConstraint(
            ["context_id", "account_id"],
            ["discovery_contexts.id", "discovery_contexts.account_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["id", "current_version"],
            ["private_pass_revisions.pass_id", "private_pass_revisions.version"],
            name="fk_private_pass_current_revision",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint("current_version > 0", name="positive_version"),
        CheckConstraint("account_id <> target_id", name="different_participants"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    context_id: Mapped[UUID] = mapped_column()
    target_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    current_version: Mapped[int] = mapped_column()


class PrivatePassRevisionRecord(Base):
    __tablename__ = "private_pass_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["pass_id", "context_id", "target_id"],
            ["private_passes.id", "private_passes.context_id", "private_passes.target_id"],
            name="fk_private_pass_revision_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["pass_id", "account_id"],
            ["private_passes.id", "private_passes.account_id"],
            name="fk_private_pass_revision_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("pass_id", "version", "account_id", name="uq_private_pass_revision_owner"),
        UniqueConstraint("account_id", "decision_sequence", name="uq_private_pass_decision"),
        UniqueConstraint(
            "pass_id", "version", "account_id", "passed", name="uq_private_pass_revision_outcome"
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("decision_sequence > 0", name="positive_sequence"),
    )
    pass_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column()
    context_id: Mapped[UUID] = mapped_column()
    target_id: Mapped[UUID] = mapped_column()
    passed: Mapped[bool] = mapped_column()
    decision_sequence: Mapped[int] = mapped_column()
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PrivatePassIntentRecord(Base):
    __tablename__ = "private_pass_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["pass_id", "result_version", "account_id"],
            [
                "private_pass_revisions.pass_id",
                "private_pass_revisions.version",
                "private_pass_revisions.account_id",
            ],
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
    pass_id: Mapped[UUID] = mapped_column()
    result_version: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
