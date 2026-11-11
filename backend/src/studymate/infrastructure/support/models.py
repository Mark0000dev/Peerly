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
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class SupportProofRecord(Base):
    __tablename__ = "support_proofs"
    __table_args__ = (
        Index("ix_support_proofs_source", "source_digest"),
        CheckConstraint(
            "octet_length(digest) = 32 AND octet_length(source_digest) = 32", name="digest_lengths"
        ),
        CheckConstraint("expires_at > created_at", name="ordered_expiry"),
    )
    digest: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    source_digest: Mapped[bytes] = mapped_column(LargeBinary(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SupportPreparationRecord(Base):
    __tablename__ = "support_preparations"
    __table_args__ = (
        Index("ix_support_preparations_source_created", "source_digest", "created_at"),
        CheckConstraint("octet_length(source_digest) = 32", name="digest_length"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_digest: Mapped[bytes] = mapped_column(LargeBinary(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SupportCaseRecord(Base):
    __tablename__ = "support_cases"
    __table_args__ = (
        CheckConstraint(
            "http_request_id IS NOT NULL OR "
            "(action_id IS NULL AND trace_id IS NULL AND span_id IS NULL)",
            name="origin_request_context",
        ),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR "
            "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
            "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0', 32) AND "
            "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))",
            name="origin_trace_pair",
        ),
        Index("ix_support_cases_proof_received", "proof_digest", "received_at"),
        Index("ix_support_cases_actor_received", "actor_id", "received_at", "id"),
        Index("ix_support_cases_received_id", "received_at", "id"),
        CheckConstraint(
            "topic IN ('cannot_sign_in','email_not_accepted','code_not_arriving',"
            "'email_already_in_use','deleted_account','other')",
            name="known_topic",
        ),
        CheckConstraint("length(btrim(message)) BETWEEN 1 AND 4000", name="bounded_message"),
        CheckConstraint("length(reply_address) BETWEEN 3 AND 254", name="bounded_reply"),
        CheckConstraint(
            "details IS NULL OR length(btrim(details)) BETWEEN 1 AND 2000", name="bounded_details"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    proof_digest: Mapped[bytes] = mapped_column(
        LargeBinary(32), ForeignKey("support_proofs.digest")
    )
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"))
    topic: Mapped[str] = mapped_column(String(32))
    reply_address: Mapped[str] = mapped_column(String(254))
    message: Mapped[str] = mapped_column(String(4000))
    details: Mapped[str | None] = mapped_column(String(2000))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    http_request_id: Mapped[UUID | None]
    action_id: Mapped[UUID | None]
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class SupportRevisionRecord(Base):
    __tablename__ = "support_case_revisions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="positive_version"),
        ForeignKeyConstraint(
            ["changed_by_id", "operator_access_version"],
            ["operator_access_revisions.account_id", "operator_access_revisions.version"],
        ),
        CheckConstraint(
            "(version = 1 AND status = 'received' AND changed_by_id IS NULL "
            "AND operator_access_version IS NULL) OR (version > 1 AND "
            "changed_by_id IS NOT NULL AND operator_access_version IS NOT NULL)",
            name="actual_status_authority",
        ),
        CheckConstraint("status IN ('received','in_review','resolved')", name="known_status"),
    )
    case_id: Mapped[UUID] = mapped_column(ForeignKey("support_cases.id"), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    changed_by_id: Mapped[UUID | None]
    operator_access_version: Mapped[int | None]


class SupportIntentRecord(Base):
    __tablename__ = "support_case_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "result_version"],
            ["support_case_revisions.case_id", "support_case_revisions.version"],
        ),
        CheckConstraint("octet_length(fingerprint) = 32", name="fingerprint_length"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="valid_key"),
    )
    proof_digest: Mapped[bytes] = mapped_column(
        LargeBinary(32), ForeignKey("support_proofs.digest"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    case_id: Mapped[UUID] = mapped_column(ForeignKey("support_cases.id"))
    result_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SupportOperatorIntentRecord(Base):
    __tablename__ = "support_operator_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "result_version"],
            ["support_case_revisions.case_id", "support_case_revisions.version"],
        ),
        CheckConstraint("octet_length(fingerprint) = 32", name="fingerprint_length"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="valid_key"),
    )
    operator_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    case_id: Mapped[UUID] = mapped_column(ForeignKey("support_cases.id"))
    result_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
