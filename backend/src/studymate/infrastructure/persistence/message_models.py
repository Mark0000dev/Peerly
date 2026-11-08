"""Retained terminal operations and immutable text messages."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
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


class MessageOperationRecord(Base):
    __tablename__ = "message_operations"
    __table_args__ = (
        UniqueConstraint("id", "author_id", "state", name="uq_message_operations_owned_state"),
        UniqueConstraint(
            "conversation_id",
            "author_id",
            "client_message_id",
            name="uq_message_operations_logical_send",
        ),
        UniqueConstraint(
            "id",
            "conversation_id",
            "low_id",
            "high_id",
            "author_id",
            "client_message_id",
            "state",
            name="uq_message_operations_owned_outcome",
        ),
        UniqueConstraint(
            "id", "author_id", "conversation_id", name="uq_message_operations_owned_scope"
        ),
        ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["message_id", "id"],
            ["messages.id", "messages.operation_id"],
            name="fk_message_operations_actual_message",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint("low_id < high_id", name="canonical_pair"),
        CheckConstraint("author_id IN (low_id, high_id)", name="participant_author"),
        CheckConstraint(
            "(state='confirmed' AND message_id IS NOT NULL AND cancelled_at IS NULL) OR "
            "(state='cancelled' AND message_id IS NULL AND cancelled_at IS NOT NULL)",
            name="terminal_outcome_shape",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    author_id: Mapped[UUID] = mapped_column()
    client_message_id: Mapped[UUID] = mapped_column()
    state: Mapped[str] = mapped_column(String(16))
    message_id: Mapped[UUID | None] = mapped_column()
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageRecord(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "id", "conversation_id", "author_id", name="uq_messages_owned_conversation_author"
        ),
        UniqueConstraint(
            "id",
            "conversation_id",
            "author_id",
            "client_message_id",
            "image_id",
            "image_version",
            "image_attempt_id",
            "image_state",
            name="uq_messages_report_image_source",
        ),
        UniqueConstraint("conversation_id", "sequence", name="uq_messages_conversation_sequence"),
        UniqueConstraint("id", "operation_id", name="uq_messages_terminal_root"),
        UniqueConstraint("operation_id", name="uq_messages_operation"),
        ForeignKeyConstraint(
            [
                "operation_id",
                "conversation_id",
                "low_id",
                "high_id",
                "author_id",
                "client_message_id",
                "state",
            ],
            [
                "message_operations.id",
                "message_operations.conversation_id",
                "message_operations.low_id",
                "message_operations.high_id",
                "message_operations.author_id",
                "message_operations.client_message_id",
                "message_operations.state",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "author_id",
                "conversation_id",
                "client_message_id",
                "image_id",
                "image_version",
                "image_state",
            ],
            [
                "chat_image_revisions.account_id",
                "chat_image_revisions.conversation_id",
                "chat_image_revisions.client_message_id",
                "chat_image_revisions.image_id",
                "chat_image_revisions.version",
                "chat_image_revisions.state",
            ],
            name="fk_messages_owned_ready_image",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["image_id", "image_version", "image_attempt_id", "image_state"],
            [
                "chat_image_revisions.image_id",
                "chat_image_revisions.version",
                "chat_image_revisions.attempt_id",
                "chat_image_revisions.state",
            ],
            name="fk_messages_actual_image_rendition",
            ondelete="RESTRICT",
        ),
        CheckConstraint("text IS NOT NULL OR image_id IS NOT NULL", name="content_required"),
        CheckConstraint(
            "(image_id IS NULL AND image_version IS NULL AND "
            "image_attempt_id IS NULL AND image_state IS NULL) OR "
            "(image_id IS NOT NULL AND image_version IS NOT NULL AND image_version>0 AND "
            "image_attempt_id IS NOT NULL AND image_state IS NOT NULL AND image_state='ready')",
            name="image_source_shape",
        ),
        CheckConstraint("state='confirmed'", name="confirmed_state"),
        CheckConstraint("sequence > 0", name="positive_sequence"),
        CheckConstraint(
            "text IS NULL OR (length(text) BETWEEN 1 AND 2000 AND text ~ '[^[:space:]]')",
            name="nonblank_bounded_text",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    operation_id: Mapped[UUID] = mapped_column()
    conversation_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    author_id: Mapped[UUID] = mapped_column()
    client_message_id: Mapped[UUID] = mapped_column()
    state: Mapped[str] = mapped_column(String(16))
    sequence: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str | None] = mapped_column(String(2000))
    image_id: Mapped[UUID | None] = mapped_column()
    image_version: Mapped[int | None] = mapped_column()
    image_attempt_id: Mapped[UUID | None] = mapped_column()
    image_state: Mapped[str | None] = mapped_column(String(16))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MessageCommandIntentRecord(Base):
    __tablename__ = "message_command_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["result_operation_id", "actor_id", "conversation_id"],
            [
                "message_operations.id",
                "message_operations.author_id",
                "message_operations.conversation_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("operation IN ('send','cancel')", name="operation_kind"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_length"),
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    operation: Mapped[str] = mapped_column(String(16), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    result_operation_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


Index(
    "ix_messages_conversation_activity", MessageRecord.conversation_id, MessageRecord.sent_at.desc()
)
