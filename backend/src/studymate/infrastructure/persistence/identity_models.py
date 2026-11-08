"""Identity storage. ORM records stay inside persistence adapters."""

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


class AccountRecord(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_version IS NULL OR lifecycle_version>0", name="lifecycle_source_version"
        ),
        ForeignKeyConstraint(
            ["id", "lifecycle_version"],
            ["account_lifecycle_revisions.account_id", "account_lifecycle_revisions.version"],
            name="fk_accounts_current_lifecycle_source",
            ondelete="RESTRICT",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_version: Mapped[int | None] = mapped_column()


class ExternalIdentityRecord(Base):
    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_external_identities_issuer_subject"),
        UniqueConstraint("account_id", name="uq_external_identities_account_id"),
        CheckConstraint("issuer = 'https://accounts.google.com'", name="google_issuer"),
        CheckConstraint("length(subject) > 0", name="nonempty_subject"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    issuer: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionRecord(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("secret_digest", name="uq_sessions_secret_digest"),
        UniqueConstraint("id", "account_id", name="uq_sessions_id_account_id"),
        CheckConstraint("octet_length(secret_digest) = 32", name="secret_digest_length"),
        CheckConstraint("expires_at > issued_at", name="expiry_after_issuance"),
        CheckConstraint("revoked_at IS NULL OR revoked_at >= issued_at", name="valid_revocation"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    secret_digest: Mapped[bytes] = mapped_column(LargeBinary)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InstitutionalBindingRecord(Base):
    __tablename__ = "institutional_bindings"
    __table_args__ = (
        UniqueConstraint("email", name="uq_institutional_bindings_email"),
        CheckConstraint(
            "email = lower(btrim(email)) AND "
            "email ~ '^[a-z0-9!#$%&''*+/=?^_`{|}~-]+"
            "(\\.[a-z0-9!#$%&''*+/=?^_`{|}~-]+)*@mail\\.apu\\.edu\\.my$' "
            "AND length(split_part(email, '@', 1)) <= 64",
            name="canonical_student_email",
        ),
        CheckConstraint("revoked_at IS NULL OR revoked_at >= verified_at", name="valid_revocation"),
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String(254))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginFlowRecord(Base):
    __tablename__ = "login_transactions"
    __table_args__ = (
        UniqueConstraint("state_digest", name="uq_login_transactions_state_digest"),
        CheckConstraint(
            "octet_length(state_digest) = 32 AND octet_length(browser_digest) = 32 "
            "AND octet_length(source_digest) = 32",
            name="digest_lengths",
        ),
        CheckConstraint("expires_at > created_at", name="valid_expiry"),
        CheckConstraint("return_to IN ('/', '/onboarding')", name="local_return_route"),
        CheckConstraint(
            "(consumed_at IS NULL AND sealed_material IS NOT NULL) OR "
            "(consumed_at IS NOT NULL AND sealed_material IS NULL)",
            name="consumed_erases_material",
        ),
        CheckConstraint(
            "completed_at IS NULL OR (consumed_at IS NOT NULL AND completed_at >= consumed_at)",
            name="completion_after_consumption",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    state_digest: Mapped[bytes] = mapped_column(LargeBinary)
    browser_digest: Mapped[bytes] = mapped_column(LargeBinary, index=True)
    source_digest: Mapped[bytes] = mapped_column(LargeBinary, index=True)
    sealed_material: Mapped[bytes | None] = mapped_column(LargeBinary)
    return_to: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
