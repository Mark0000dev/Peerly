"""Unregistered actual manual mutation sources; main owns58 DDL and metadata wiring."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class OperatorMembershipVerificationRecord(Base):
    __tablename__ = "operator_membership_verifications"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_operator_manual_membership_target"),
        UniqueConstraint("challenge_id", name="uq_operator_manual_membership_challenge"),
        UniqueConstraint("event_id", name="uq_operator_manual_membership_event"),
        UniqueConstraint("id", "operator_id", name="uq_operator_manual_membership_actor_source"),
        ForeignKeyConstraint(
            ["google_identity_id", "account_id"],
            ["external_identities.id", "external_identities.account_id"],
            ondelete="RESTRICT",
            name="fk_manual_membership_google",
        ),
        ForeignKeyConstraint(
            ["challenge_id", "account_id", "email"],
            ["email_challenges.id", "email_challenges.account_id", "email_challenges.email"],
            ondelete="RESTRICT",
            name="fk_manual_membership_submission",
        ),
        ForeignKeyConstraint(
            ["account_id", "email", "verified_at"],
            [
                "institutional_bindings.account_id",
                "institutional_bindings.email",
                "institutional_bindings.verified_at",
            ],
            ondelete="RESTRICT",
            name="fk_manual_membership_binding",
        ),
        ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            ondelete="RESTRICT",
            name="fk_manual_membership_grant",
        ),
        ForeignKeyConstraint(
            ["actor_session_id", "operator_id"],
            ["sessions.id", "sessions.account_id"],
            ondelete="RESTRICT",
            name="fk_manual_membership_session",
        ),
        ForeignKeyConstraint(
            ["event_id", "account_id", "event_kind", "verified_at"],
            [
                "product_events.id",
                "product_events.account_id",
                "product_events.kind",
                "product_events.occurred_at",
            ],
            ondelete="RESTRICT",
            name="fk_manual_membership_event",
        ),
        CheckConstraint(
            "operator_access_active=true AND operator_access_version>0", name="actual_active_grant"
        ),
        CheckConstraint("event_kind='auth.email_confirmed'", name="actual_membership_event"),
        CheckConstraint(
            "email !~ '^peerly-stage-[0-9a-f]{32}@mail[.]apu[.]edu[.]my$'",
            name="no_staging_placeholder",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column()
    google_identity_id: Mapped[UUID] = mapped_column()
    challenge_id: Mapped[UUID] = mapped_column()
    email: Mapped[str] = mapped_column(String(254))
    operator_id: Mapped[UUID] = mapped_column()
    operator_access_version: Mapped[int] = mapped_column()
    operator_access_active: Mapped[bool] = mapped_column()
    actor_session_id: Mapped[UUID] = mapped_column()
    event_id: Mapped[UUID] = mapped_column()
    event_kind: Mapped[str] = mapped_column(String(32))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OperatorMembershipIntentRecord(Base):
    __tablename__ = "operator_membership_verification_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["verification_id", "operator_id"],
            [
                "operator_membership_verifications.id",
                "operator_membership_verifications.operator_id",
            ],
            ondelete="RESTRICT",
            name="fk_manual_membership_intent_source",
        ),
        UniqueConstraint("verification_id", name="uq_manual_membership_intent_source"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="valid_key"),
        CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_length"),
    )
    operator_id: Mapped[UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    verification_id: Mapped[UUID] = mapped_column()
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
