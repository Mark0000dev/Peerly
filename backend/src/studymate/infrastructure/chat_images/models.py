"""Owned image sources and attempts, registered with paired migration0041."""

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

FAILURE_SHAPE = (
    "failure IS NULL OR failure IN ('invalid_image','unsupported_format','too_large',"
    "'dimensions_exceeded','animated_image','content_changed','account_unavailable',"
    "'contact_unavailable','storage_unavailable','processing_unavailable')"
)


class ChatImageRecord(Base):
    __tablename__ = "chat_image_preparations"
    __table_args__ = (
        UniqueConstraint("id", "account_id", name="uq_chat_images_id_owner"),
        UniqueConstraint(
            "id",
            "account_id",
            "conversation_id",
            "client_message_id",
            name="uq_chat_images_owned_message",
        ),
        UniqueConstraint(
            "account_id",
            "conversation_id",
            "client_message_id",
            name="uq_chat_images_client_message",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["id", "current_version"],
            ["chat_image_revisions.image_id", "chat_image_revisions.version"],
            name="fk_chat_images_current_revision",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "account_id IN (low_id,high_id) AND low_id < high_id", name="actual_participant"
        ),
        CheckConstraint("current_version > 0", name="positive_version"),
        CheckConstraint("source_size BETWEEN 1 AND 10000000", name="bounded_source"),
        CheckConstraint("octet_length(source_digest)=32", name="source_digest"),
        CheckConstraint("content_type IN ('image/jpeg','image/png')", name="supported_type"),
        CheckConstraint(
            "created_at < upload_expires_at AND upload_expires_at <= processing_expires_at",
            name="ordered_deadlines",
        ),
        Index("ix_chat_images_account_created", "account_id", "created_at"),
        Index("ix_chat_images_conversation_owner", "conversation_id", "account_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    conversation_id: Mapped[UUID] = mapped_column()
    low_id: Mapped[UUID] = mapped_column()
    high_id: Mapped[UUID] = mapped_column()
    client_message_id: Mapped[UUID] = mapped_column()
    current_version: Mapped[int] = mapped_column()
    source_size: Mapped[int] = mapped_column()
    source_digest: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    upload_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processing_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatImageRevisionRecord(Base):
    __tablename__ = "chat_image_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["image_id", "account_id", "conversation_id", "client_message_id"],
            [
                "chat_image_preparations.id",
                "chat_image_preparations.account_id",
                "chat_image_preparations.conversation_id",
                "chat_image_preparations.client_message_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["image_id", "attempt_id"],
            ["chat_image_attempts.image_id", "chat_image_attempts.id"],
            name="fk_chat_image_revision_attempt",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["image_id", "attempt_id", "ready_attempt_outcome"],
            [
                "chat_image_attempts.image_id",
                "chat_image_attempts.id",
                "chat_image_attempts.outcome",
            ],
            name="fk_chat_image_actual_ready_attempt",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "account_id",
            "conversation_id",
            "client_message_id",
            "image_id",
            "version",
            name="uq_chat_image_revision_owned_message",
        ),
        UniqueConstraint(
            "account_id",
            "conversation_id",
            "client_message_id",
            "image_id",
            "version",
            "state",
            name="uq_chat_image_revision_owned_state",
        ),
        UniqueConstraint(
            "image_id", "version", "attempt_id", "state", name="uq_chat_image_revision_rendition"
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "state IN ('uploading','queued','processing','ready','rejected','cancelled','expired')",
            name="known_state",
        ),
        CheckConstraint("(state='rejected')=(failure IS NOT NULL)", name="failure_required"),
        CheckConstraint(FAILURE_SHAPE, name="known_failure"),
        CheckConstraint(
            "state NOT IN ('processing','ready') OR attempt_id IS NOT NULL", name="attempt_required"
        ),
        CheckConstraint(
            "(state='ready' AND ready_attempt_outcome IS NOT NULL AND "
            "ready_attempt_outcome='ready') OR "
            "(state<>'ready' AND ready_attempt_outcome IS NULL)",
            name="ready_attempt_required",
        ),
        Index("ix_chat_image_revisions_state", "state", "updated_at"),
    )
    image_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column()
    conversation_id: Mapped[UUID] = mapped_column()
    client_message_id: Mapped[UUID] = mapped_column()
    state: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempt_id: Mapped[UUID | None] = mapped_column()
    ready_attempt_outcome: Mapped[str | None] = mapped_column(String(16))
    failure: Mapped[str | None] = mapped_column(String(32))


class ChatImageAttemptRecord(Base):
    __tablename__ = "chat_image_attempts"
    __table_args__ = (
        UniqueConstraint("image_id", "id", name="uq_chat_image_attempt_source"),
        UniqueConstraint("image_id", "id", "outcome", name="uq_chat_image_attempt_outcome"),
        UniqueConstraint("image_id", "number", name="uq_chat_image_attempt_number"),
        CheckConstraint("number BETWEEN 1 AND 3", name="bounded_number"),
        CheckConstraint("lease_until > started_at", name="ordered_lease"),
        CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="ordered_finish"),
        CheckConstraint(
            "outcome IN ('processing','ready','retry','rejected','stale','interrupted')",
            name="known_outcome",
        ),
        CheckConstraint("(outcome='processing')=(finished_at IS NULL)", name="finish_required"),
        CheckConstraint("(outcome='retry')=(next_attempt_at IS NOT NULL)", name="retry_required"),
        CheckConstraint(
            "next_attempt_at IS NULL OR next_attempt_at > finished_at", name="ordered_retry"
        ),
        CheckConstraint(FAILURE_SHAPE, name="known_failure"),
        CheckConstraint(
            "(display_size IS NULL AND display_width IS NULL AND display_height IS NULL "
            "AND display_digest IS NULL) OR "
            "(display_size IS NOT NULL AND display_width IS NOT NULL AND display_height "
            "IS NOT NULL AND display_digest IS NOT NULL "
            "AND display_size > 0 AND display_width BETWEEN 1 AND 1024 AND "
            "display_height BETWEEN 1 AND 1024 "
            "AND octet_length(display_digest)=32)",
            name="display_metadata",
        ),
        CheckConstraint("outcome<>'ready' OR display_digest IS NOT NULL", name="ready_metadata"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    image_id: Mapped[UUID] = mapped_column(
        ForeignKey("chat_image_preparations.id", ondelete="RESTRICT")
    )
    number: Mapped[int] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(16))
    failure: Mapped[str | None] = mapped_column(String(32))
    display_width: Mapped[int | None] = mapped_column()
    display_height: Mapped[int | None] = mapped_column()
    display_size: Mapped[int | None] = mapped_column()
    display_digest: Mapped[bytes | None] = mapped_column(LargeBinary)


class ChatImageIntentRecord(Base):
    __tablename__ = "chat_image_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "conversation_id", "client_message_id", "image_id", "result_version"],
            [
                "chat_image_revisions.account_id",
                "chat_image_revisions.conversation_id",
                "chat_image_revisions.client_message_id",
                "chat_image_revisions.image_id",
                "chat_image_revisions.version",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("operation IN ('start','finalize','cancel')", name="known_operation"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_length"),
        CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND "
            "span_id IS NULL)",
            name="origin_request_context",
        ),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND span_id"
            " IS NOT NULL "
            "AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0',32) "
            "AND span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0',16))",
            name="origin_trace_pair",
        ),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    operation: Mapped[str] = mapped_column(String(16), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    conversation_id: Mapped[UUID] = mapped_column()
    client_message_id: Mapped[UUID] = mapped_column()
    image_id: Mapped[UUID] = mapped_column()
    result_version: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


CHAT_IMAGE_MODELS = (
    ChatImageRecord,
    ChatImageRevisionRecord,
    ChatImageAttemptRecord,
    ChatImageIntentRecord,
)
