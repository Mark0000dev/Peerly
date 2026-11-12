"""Retained operator manual-membership source and actor-bound idempotency."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058_manual_membership"
down_revision: str | Sequence[str] | None = "0057_operator_audit_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_external_identities_membership_source", "external_identities", ["id", "account_id"]
    )
    op.create_unique_constraint(
        "uq_email_challenges_membership_source", "email_challenges", ["id", "account_id", "email"]
    )
    op.create_unique_constraint(
        "uq_institutional_bindings_membership_source",
        "institutional_bindings",
        ["account_id", "email", "verified_at"],
    )
    op.create_unique_constraint(
        "uq_product_events_membership_source",
        "product_events",
        ["id", "account_id", "kind", "occurred_at"],
    )
    op.create_table(
        "operator_membership_verifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("google_identity_id", sa.Uuid(), nullable=False),
        sa.Column("challenge_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("operator_access_version", sa.Integer(), nullable=False),
        sa.Column("operator_access_active", sa.Boolean(), nullable=False),
        sa.Column("actor_session_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_kind", sa.String(32), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", name="uq_operator_manual_membership_target"),
        sa.UniqueConstraint("challenge_id", name="uq_operator_manual_membership_challenge"),
        sa.UniqueConstraint("event_id", name="uq_operator_manual_membership_event"),
        sa.UniqueConstraint("id", "operator_id", name="uq_operator_manual_membership_actor_source"),
        sa.ForeignKeyConstraint(
            ["google_identity_id", "account_id"],
            ["external_identities.id", "external_identities.account_id"],
            ondelete="RESTRICT",
            name="fk_manual_membership_google",
        ),
        sa.ForeignKeyConstraint(
            ["challenge_id", "account_id", "email"],
            ["email_challenges.id", "email_challenges.account_id", "email_challenges.email"],
            ondelete="RESTRICT",
            name="fk_manual_membership_submission",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "email", "verified_at"],
            [
                "institutional_bindings.account_id",
                "institutional_bindings.email",
                "institutional_bindings.verified_at",
            ],
            ondelete="RESTRICT",
            name="fk_manual_membership_binding",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            ondelete="RESTRICT",
            name="fk_manual_membership_grant",
        ),
        sa.ForeignKeyConstraint(
            ["actor_session_id", "operator_id"],
            ["sessions.id", "sessions.account_id"],
            ondelete="RESTRICT",
            name="fk_manual_membership_session",
        ),
        sa.ForeignKeyConstraint(
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
        sa.CheckConstraint(
            "operator_access_active=true AND operator_access_version>0",
            name=op.f("ck_operator_membership_verifications_actual_active_grant"),
        ),
        sa.CheckConstraint(
            "event_kind='auth.email_confirmed'",
            name=op.f("ck_operator_membership_verifications_actual_membership_event"),
        ),
        sa.CheckConstraint(
            "email !~ '^peerly-stage-[0-9a-f]{32}@mail[.]apu[.]edu[.]my$'",
            name=op.f("ck_operator_membership_verifications_no_staging_placeholder"),
        ),
    )
    op.create_table(
        "operator_membership_verification_intents",
        sa.Column("operator_id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("verification_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["verification_id", "operator_id"],
            [
                "operator_membership_verifications.id",
                "operator_membership_verifications.operator_id",
            ],
            ondelete="RESTRICT",
            name="fk_manual_membership_intent_source",
        ),
        sa.UniqueConstraint("verification_id", name="uq_manual_membership_intent_source"),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'",
            name=op.f("ck_operator_membership_verification_intents_valid_key"),
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint)=32",
            name=op.f("ck_operator_membership_verification_intents_fingerprint_length"),
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM operator_membership_verifications "
            "UNION ALL SELECT 1 FROM operator_membership_verification_intents)"
        )
    ):
        raise RuntimeError("Refusing to remove retained manual membership verification facts")
    op.drop_table("operator_membership_verification_intents")
    op.drop_table("operator_membership_verifications")
    for table, name in (
        ("product_events", "uq_product_events_membership_source"),
        ("institutional_bindings", "uq_institutional_bindings_membership_source"),
        ("email_challenges", "uq_email_challenges_membership_source"),
        ("external_identities", "uq_external_identities_membership_source"),
    ):
        op.drop_constraint(name, table, type_="unique")
