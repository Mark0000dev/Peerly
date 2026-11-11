"""Actor-bound institutional challenges, stable intents and encrypted delivery outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_email_verification"
down_revision: str | Sequence[str] | None = "0002_login_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("code_digest", sa.LargeBinary(), nullable=True),
        sa.Column("source_digest", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resend_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "email = lower(btrim(email)) AND email ~ '^[a-z0-9!#$%&''*+/=?^_`{|}~-"
            "]+(\\.[a-z0-9!#$%&''*+/=?^_`{|}~-]+)*@mail\\.apu\\.edu\\.my$' AND "
            "length(split_part(email, '@', 1)) <= 64",
            name=op.f("ck_email_challenges_canonical_student_email"),
        ),
        sa.CheckConstraint(
            "NOT (consumed_at IS NOT NULL AND superseded_at IS NOT NULL)",
            name=op.f("ck_email_challenges_exclusive_terminal_state"),
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 5", name=op.f("ck_email_challenges_attempts_range")
        ),
        sa.CheckConstraint(
            "code_digest IS NULL OR octet_length(code_digest) = 32",
            name=op.f("ck_email_challenges_code_digest_length"),
        ),
        sa.CheckConstraint(
            "created_at < resend_at AND resend_at < expires_at",
            name=op.f("ck_email_challenges_valid_deadlines"),
        ),
        sa.CheckConstraint(
            "octet_length(source_digest) = 32",
            name=op.f("ck_email_challenges_source_digest_length"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_email_challenges_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "account_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_email_challenges_session_account",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_challenges")),
        sa.UniqueConstraint("id", "account_id", name="uq_email_challenges_id_account_id"),
    )
    op.create_index(
        "ix_email_challenges_account_created",
        "email_challenges",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_email_challenges_email_created",
        "email_challenges",
        ["email", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_email_challenges_source_created",
        "email_challenges",
        ["source_digest", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_email_challenges_current_account",
        "email_challenges",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL AND superseded_at IS NULL"),
    )
    op.create_table(
        "email_intents",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("challenge_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("attempts_remaining", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(operation = 'start' AND outcome IS NULL AND attempts_remaining IS NULL)"
            " OR (operation = 'verify' AND outcome IS NOT NULL AND attempts_remaining"
            " BETWEEN 0 AND 5)",
            name=op.f("ck_email_intents_result_shape"),
        ),
        sa.CheckConstraint(
            "(outcome = 'verified' AND verified_at IS NOT NULL) OR ((outcome IS NULL "
            "OR outcome != 'verified') AND verified_at IS NULL)",
            name=op.f("ck_email_intents_verification_timestamp"),
        ),
        sa.CheckConstraint(
            "operation IN ('start', 'verify')", name=op.f("ck_email_intents_known_operation")
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('verified', 'wrong', 'locked', 'expired',"
            " 'unavailable', 'support_required')",
            name=op.f("ck_email_intents_known_outcome"),
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32", name=op.f("ck_email_intents_fingerprint_length")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_email_intents_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["challenge_id", "account_id"],
            ["email_challenges.id", "email_challenges.account_id"],
            name="fk_email_intents_challenge_account",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("account_id", "operation", "key", name=op.f("pk_email_intents")),
    )
    op.create_index(
        "uq_email_intents_consumption",
        "email_intents",
        ["challenge_id"],
        unique=True,
        postgresql_where=sa.text(
            "operation = 'verify' AND outcome IN ('verified', 'support_required')"
        ),
    )
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("challenge_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("sealed_envelope", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_generation", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "(status IN ('queued', 'inflight') AND sealed_envelope IS NOT NULL) OR "
            "(status IN ('delivered', 'failed', 'cancelled') AND sealed_envelope IS "
            "NULL)",
            name=op.f("ck_email_outbox_envelope_lifecycle"),
        ),
        sa.CheckConstraint(
            "last_error IS NULL OR last_error IN ('provider_unavailable', "
            "'provider_rejected', 'envelope_invalid', 'delivery_expired')",
            name=op.f("ck_email_outbox_safe_error_code"),
        ),
        sa.CheckConstraint(
            "status != 'inflight' OR lease_until IS NOT NULL",
            name=op.f("ck_email_outbox_inflight_lease"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'inflight', 'delivered', 'failed', 'cancelled')",
            name=op.f("ck_email_outbox_known_status"),
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 3 AND lease_generation >= 0",
            name=op.f("ck_email_outbox_attempts_and_generation"),
        ),
        sa.ForeignKeyConstraint(
            ["challenge_id"],
            ["email_challenges.id"],
            name=op.f("fk_email_outbox_challenge_id_email_challenges"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
        sa.UniqueConstraint("challenge_id", name="uq_email_outbox_challenge_id"),
    )
    op.create_index("ix_email_outbox_due", "email_outbox", ["status", "due_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_email_outbox_due", table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_index("uq_email_intents_consumption", table_name="email_intents")
    op.drop_table("email_intents")
    op.drop_index(
        "uq_email_challenges_current_account",
        table_name="email_challenges",
        postgresql_where=sa.text("consumed_at IS NULL AND superseded_at IS NULL"),
    )
    op.drop_index("ix_email_challenges_source_created", table_name="email_challenges")
    op.drop_index("ix_email_challenges_email_created", table_name="email_challenges")
    op.drop_index("ix_email_challenges_account_created", table_name="email_challenges")
    op.drop_table("email_challenges")
