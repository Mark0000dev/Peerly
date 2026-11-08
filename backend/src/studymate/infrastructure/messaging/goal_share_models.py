"""Owner-registered0033 immutable goal-share sources, heads and original receipts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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


class ConversationGoalShareRecord(Base):
    __tablename__ = "conversation_goal_shares"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "context_version", name="uq_conversation_goal_shares_version"
        ),
        UniqueConstraint(
            "id", "owner_id", "conversation_id", name="uq_conversation_goal_shares_owner"
        ),
        UniqueConstraint(
            "id",
            "owner_id",
            "conversation_id",
            "context_version",
            name="uq_conversation_goal_shares_source",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "goal_id", "goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("low_id < high_id", name="canonical_pair"),
        CheckConstraint("owner_id IN (low_id, high_id)", name="participant_owner"),
        CheckConstraint(
            "goal_version > 0 AND context_version > 0", name="positive_source_versions"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    owner_id: Mapped[UUID] = mapped_column()
    goal_id: Mapped[UUID] = mapped_column()
    goal_version: Mapped[int] = mapped_column()
    context_version: Mapped[int] = mapped_column(BigInteger)
    shared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class ConversationGoalShareHeadRecord(Base):
    __tablename__ = "conversation_goal_share_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "context_version"],
            [
                "conversation_goal_shares.conversation_id",
                "conversation_goal_shares.context_version",
            ],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("context_version > 0", name="actual_shared_context"),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), primary_key=True
    )
    context_version: Mapped[int] = mapped_column(BigInteger)


class ConversationGoalShareIntentRecord(Base):
    __tablename__ = "conversation_goal_share_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["result_share_id", "actor_id", "conversation_id"],
            [
                "conversation_goal_shares.id",
                "conversation_goal_shares.owner_id",
                "conversation_goal_shares.conversation_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        CheckConstraint("octet_length(fingerprint) = 32", name="fingerprint_length"),
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT")
    )
    result_share_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
