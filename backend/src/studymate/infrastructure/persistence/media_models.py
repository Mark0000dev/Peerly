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


class PhotoUploadRecord(Base):
    __tablename__ = "photo_uploads"
    __table_args__ = (
        UniqueConstraint("id", "account_id", name="uq_photo_uploads_owner"),
        ForeignKeyConstraint(
            ["id", "current_version"],
            ["photo_upload_revisions.upload_id", "photo_upload_revisions.version"],
            name="fk_photo_uploads_current_revision",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "current_version > 0 AND expected_photo_version >= 0", name="positive_versions"
        ),
        CheckConstraint("source_size BETWEEN 1 AND 10000000", name="bounded_source"),
        CheckConstraint("octet_length(source_digest) = 32", name="digest_length"),
        CheckConstraint("content_type IN ('image/jpeg', 'image/png')", name="supported_type"),
        CheckConstraint(
            "upload_expires_at > created_at AND processing_expires_at >= upload_expires_at",
            name="ordered_deadlines",
        ),
        Index("ix_photo_uploads_owner_created", "account_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    current_version: Mapped[int] = mapped_column()
    expected_photo_version: Mapped[int] = mapped_column()
    source_size: Mapped[int] = mapped_column()
    source_digest: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    upload_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processing_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PhotoUploadRevisionRecord(Base):
    __tablename__ = "photo_upload_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["upload_id", "account_id"],
            ["photo_uploads.id", "photo_uploads.account_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["upload_id", "attempt_id"],
            ["photo_processing_attempts.upload_id", "photo_processing_attempts.id"],
            name="fk_photo_upload_revisions_attempt",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "account_id", "upload_id", "version", name="uq_photo_upload_revisions_owner"
        ),
        UniqueConstraint(
            "account_id",
            "upload_id",
            "version",
            "state",
            name="uq_photo_upload_revisions_owner_state",
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "state IN ('uploading', 'queued', 'processing', 'ready', "
            "'rejected', 'cancelled', 'expired')",
            name="known_state",
        ),
        CheckConstraint("(state = 'rejected') = (failure IS NOT NULL)", name="failure_required"),
        CheckConstraint(
            "failure IS NULL OR failure IN ('invalid_image', 'unsupported_format', 'too_large', "
            "'dimensions_exceeded', 'animated_image', 'content_changed', 'photo_changed', "
            "'account_unavailable', 'storage_unavailable', 'processing_unavailable')",
            name="known_failure",
        ),
        CheckConstraint(
            "state NOT IN ('processing', 'ready') OR attempt_id IS NOT NULL",
            name="attempt_required",
        ),
        Index("ix_photo_upload_revisions_state", "state"),
    )
    upload_id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column()
    state: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempt_id: Mapped[UUID | None] = mapped_column()
    failure: Mapped[str | None] = mapped_column(String(32))


class PhotoRevisionRecord(Base):
    __tablename__ = "photo_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "upload_id", "upload_version", "upload_state"],
            [
                "photo_upload_revisions.account_id",
                "photo_upload_revisions.upload_id",
                "photo_upload_revisions.version",
                "photo_upload_revisions.state",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("upload_state = 'ready'", name="ready_upload"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[UUID] = mapped_column()
    upload_version: Mapped[int] = mapped_column()
    upload_state: Mapped[str] = mapped_column(String(16))
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PhotoRecord(Base):
    __tablename__ = "photos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "current_version"],
            ["photo_revisions.account_id", "photo_revisions.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("current_version > 0", name="positive_version"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    current_version: Mapped[int] = mapped_column()


class MediaIntentRecord(Base):
    __tablename__ = "media_write_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "upload_id", "result_version"],
            [
                "photo_upload_revisions.account_id",
                "photo_upload_revisions.upload_id",
                "photo_upload_revisions.version",
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
    upload_id: Mapped[UUID] = mapped_column()
    result_version: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
