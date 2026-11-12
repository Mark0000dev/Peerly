"""Proof-bound native login handoff. Parent must confirm revision/head before integration."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061_native_login"
down_revision: str | Sequence[str] | None = "0060_report_triage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "native_login_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("challenge", sa.String(43), nullable=False),
        sa.Column("browser_digest", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_digest", sa.LargeBinary(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_native_login_attempts"),
        sa.UniqueConstraint("browser_digest", name="uq_native_login_attempts_browser_digest"),
        sa.UniqueConstraint("source_digest", name="uq_native_login_attempts_source_digest"),
        sa.ForeignKeyConstraint(
            ["source_digest"],
            ["sessions.secret_digest"],
            ondelete="RESTRICT",
            name="fk_native_login_attempts_source_digest_sessions",
        ),
        sa.CheckConstraint(
            "length(challenge) = 43", name="ck_native_login_attempts_native_challenge_length"
        ),
        sa.CheckConstraint(
            "octet_length(browser_digest) = 32",
            name="ck_native_login_attempts_native_browser_digest_length",
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_native_login_attempts_native_expiry"
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR (source_digest IS NOT NULL AND consumed_at >= created_at)",
            name="ck_native_login_attempts_native_consumption",
        ),
        sa.CheckConstraint(
            "cancelled_at IS NULL OR (consumed_at IS NULL AND cancelled_at >= created_at)",
            name="ck_native_login_attempts_native_cancellation",
        ),
    )
    op.create_index("ix_native_login_attempts_expires_at", "native_login_attempts", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_native_login_attempts_expires_at", table_name="native_login_attempts")
    op.drop_table("native_login_attempts")
