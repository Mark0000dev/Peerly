"""Retained source-bound private read positions and original explicit acknowledgements."""

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


class ConversationReadRevisionRecord(Base):
    __tablename__ = "conversation_read_revisions"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "account_id", "version", name="uq_conversation_read_revision_version"
        ),
        UniqueConstraint(
            "id", "account_id", "conversation_id", name="uq_conversation_read_revision_owned_source"
        ),
        ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "through_sequence"],
            ["messages.conversation_id", "messages.sequence"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("account_id IN (low_id,high_id)", name="participant_reader"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("through_sequence > 0", name="positive_sequence"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column()
    account_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    through_sequence: Mapped[int] = mapped_column(BigInteger)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class ConversationReadPositionRecord(Base):
    __tablename__ = "conversation_read_positions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "account_id", "current_version"],
            [
                "conversation_read_revisions.conversation_id",
                "conversation_read_revisions.account_id",
                "conversation_read_revisions.version",
            ],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("current_version > 0", name="positive_version"),
    )
    conversation_id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(primary_key=True)
    current_version: Mapped[int] = mapped_column()


class ConversationReadIntentRecord(Base):
    __tablename__ = "conversation_read_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["result_revision_id", "account_id", "conversation_id"],
            [
                "conversation_read_revisions.id",
                "conversation_read_revisions.account_id",
                "conversation_read_revisions.conversation_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_length"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    result_revision_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
