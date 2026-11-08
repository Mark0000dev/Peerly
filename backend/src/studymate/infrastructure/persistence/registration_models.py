from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord


class PolicyDocumentRecord(Base):
    __tablename__ = "policy_documents"
    __table_args__ = (
        UniqueConstraint("kind", "version", name="uq_policy_documents_kind_version"),
        UniqueConstraint("id", "kind", name="uq_policy_documents_id_kind"),
        CheckConstraint("kind IN ('terms', 'privacy')", name="known_kind"),
        CheckConstraint("version ~ '^[A-Za-z0-9._-]{1,64}$'", name="valid_version"),
        CheckConstraint(
            "length(btrim(title)) > 0 AND length(btrim(content)) > 0", name="actual_content"
        ),
        Index("ix_policy_documents_publication", "kind", "published_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    version: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RegistrationContextRecord(Base):
    __tablename__ = "registration_contexts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "account_id"],
            [SessionRecord.id, SessionRecord.account_id],
            name="fk_registration_contexts_session_account",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["terms_id", "terms_kind"],
            [PolicyDocumentRecord.id, PolicyDocumentRecord.kind],
            name="fk_registration_contexts_terms_document",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["privacy_id", "privacy_kind"],
            [PolicyDocumentRecord.id, PolicyDocumentRecord.kind],
            name="fk_registration_contexts_privacy_document",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "terms_kind = 'terms' AND privacy_kind = 'privacy'", name="correct_document_kinds"
        ),
        UniqueConstraint(
            "account_id", "intent_key", name="uq_registration_contexts_account_intent"
        ),
        UniqueConstraint(
            "id", "account_id", "completed_at", name="uq_registration_contexts_actual_completion"
        ),
        CheckConstraint("expires_at > created_at", name="valid_expiry"),
        CheckConstraint("length(btrim(notice_text)) > 0", name="actual_notice"),
        CheckConstraint("surface = 'onboarding_completion'", name="known_surface"),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at", name="valid_completion"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey(AccountRecord.id, ondelete="RESTRICT"))
    session_id: Mapped[UUID] = mapped_column()
    terms_id: Mapped[UUID] = mapped_column()
    privacy_id: Mapped[UUID] = mapped_column()
    terms_kind: Mapped[str] = mapped_column(String(16), default="terms")
    privacy_kind: Mapped[str] = mapped_column(String(16), default="privacy")
    notice_text: Mapped[str] = mapped_column(String(512))
    surface: Mapped[str] = mapped_column(String(32))
    intent_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RegistrationReceiptRecord(Base):
    __tablename__ = "registration_receipts"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_registration_receipts_account_id"),
        UniqueConstraint("account_id", "id", name="uq_registration_receipts_owner_id"),
        UniqueConstraint("context_id", name="uq_registration_receipts_context_id"),
        ForeignKeyConstraint(
            ["context_id", "account_id", "registered_at"],
            [
                RegistrationContextRecord.id,
                RegistrationContextRecord.account_id,
                RegistrationContextRecord.completed_at,
            ],
            name="fk_registration_receipts_actual_completion",
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey(AccountRecord.id, ondelete="RESTRICT"))
    context_id: Mapped[UUID] = mapped_column()
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    intent_key: Mapped[str] = mapped_column(String(128))
