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
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord


class EmailChallengeRecord(Base):
    __tablename__ = "email_challenges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "account_id"],
            [SessionRecord.id, SessionRecord.account_id],
            name="fk_email_challenges_session_account",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "account_id", name="uq_email_challenges_id_account_id"),
        CheckConstraint("attempts BETWEEN 0 AND 5", name="attempts_range"),
        CheckConstraint(
            "created_at < resend_at AND resend_at < expires_at", name="valid_deadlines"
        ),
        CheckConstraint(
            "NOT (consumed_at IS NOT NULL AND superseded_at IS NOT NULL)",
            name="exclusive_terminal_state",
        ),
        CheckConstraint(
            "code_digest IS NULL OR octet_length(code_digest) = 32", name="code_digest_length"
        ),
        CheckConstraint("octet_length(source_digest) = 32", name="source_digest_length"),
        CheckConstraint(
            "email = lower(btrim(email)) AND "
            "email ~ '^[a-z0-9!#$%&''*+/=?^_`{|}~-]+"
            "(\\.[a-z0-9!#$%&''*+/=?^_`{|}~-]+)*@mail\\.apu\\.edu\\.my$' "
            "AND length(split_part(email, '@', 1)) <= 64",
            name="canonical_student_email",
        ),
        Index(
            "uq_email_challenges_current_account",
            "account_id",
            unique=True,
            postgresql_where=text("consumed_at IS NULL AND superseded_at IS NULL"),
        ),
        Index("ix_email_challenges_email_created", "email", "created_at"),
        Index("ix_email_challenges_source_created", "source_digest", "created_at"),
        Index("ix_email_challenges_account_created", "account_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey(AccountRecord.id, ondelete="RESTRICT"))
    session_id: Mapped[UUID] = mapped_column()
    email: Mapped[str] = mapped_column(String(254))
    code_digest: Mapped[bytes | None] = mapped_column(LargeBinary)
    source_digest: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resend_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailIntentRecord(Base):
    __tablename__ = "email_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["challenge_id", "account_id"],
            [EmailChallengeRecord.id, EmailChallengeRecord.account_id],
            name="fk_email_intents_challenge_account",
            ondelete="RESTRICT",
        ),
        CheckConstraint("operation IN ('start', 'verify')", name="known_operation"),
        Index(
            "uq_email_intents_consumption",
            "challenge_id",
            unique=True,
            postgresql_where=text(
                "operation = 'verify' AND outcome IN ('verified', 'support_required')"
            ),
        ),
        CheckConstraint("octet_length(fingerprint) = 32", name="fingerprint_length"),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('verified', 'wrong', 'locked', 'expired', "
            "'unavailable', 'support_required')",
            name="known_outcome",
        ),
        CheckConstraint(
            "(operation = 'start' AND outcome IS NULL AND attempts_remaining IS NULL) OR "
            "(operation = 'verify' AND outcome IS NOT NULL AND attempts_remaining BETWEEN"
            " 0 AND 5)",
            name="result_shape",
        ),
        CheckConstraint(
            "(outcome = 'verified' AND verified_at IS NOT NULL) OR ((outcome IS NULL OR "
            "outcome != 'verified') AND verified_at IS NULL)",
            name="verification_timestamp",
        ),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey(AccountRecord.id, ondelete="RESTRICT"), primary_key=True
    )
    operation: Mapped[str] = mapped_column(String(16), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    challenge_id: Mapped[UUID] = mapped_column()
    outcome: Mapped[str | None] = mapped_column(String(32))
    attempts_remaining: Mapped[int | None] = mapped_column()
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailDeliveryRecord(Base):
    __tablename__ = "email_outbox"
    __table_args__ = (
        UniqueConstraint("challenge_id", name="uq_email_outbox_challenge_id"),
        CheckConstraint(
            "status IN ('queued', 'inflight', 'delivered', 'failed', 'cancelled')",
            name="known_status",
        ),
        CheckConstraint(
            "attempts BETWEEN 0 AND 3 AND lease_generation >= 0", name="attempts_and_generation"
        ),
        CheckConstraint(
            "(status IN ('queued', 'inflight') AND sealed_envelope IS NOT NULL) OR "
            "(status IN ('delivered', 'failed', 'cancelled') AND sealed_envelope IS NULL)",
            name="envelope_lifecycle",
        ),
        CheckConstraint("status != 'inflight' OR lease_until IS NOT NULL", name="inflight_lease"),
        CheckConstraint(
            "last_error IS NULL OR last_error IN ('provider_unavailable', "
            "'provider_rejected', 'envelope_invalid', 'delivery_expired')",
            name="safe_error_code",
        ),
        Index("ix_email_outbox_due", "status", "due_at"),
        CheckConstraint(
            "origin_request_id IS NOT NULL OR (origin_action_id IS NULL AND "
            "origin_trace_id IS NULL AND origin_span_id IS NULL)",
            name="origin_request_context",
        ),
        CheckConstraint(
            "(origin_trace_id IS NULL AND origin_span_id IS NULL) OR "
            "(origin_trace_id IS NOT NULL AND origin_span_id IS NOT NULL AND "
            "origin_trace_id ~ '^[0-9a-f]{32}$' AND origin_trace_id != repeat('0', 32) AND "
            "origin_span_id ~ '^[0-9a-f]{16}$' AND origin_span_id != repeat('0', 16))",
            name="origin_trace_pair",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    challenge_id: Mapped[UUID] = mapped_column(
        ForeignKey(EmailChallengeRecord.id, ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(16))
    sealed_envelope: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0)
    lease_generation: Mapped[int] = mapped_column(default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(32))
    origin_request_id: Mapped[UUID | None] = mapped_column()
    origin_action_id: Mapped[UUID | None] = mapped_column()
    origin_trace_id: Mapped[str | None] = mapped_column(String(32))
    origin_span_id: Mapped[str | None] = mapped_column(String(16))
