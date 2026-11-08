"""Independent persistent callback-failure budget without raw authentication data."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_callback_attempts"
down_revision: str | Sequence[str] | None = "0004_registration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_callback_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_digest", sa.LargeBinary(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_login_callback_attempts"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_login_callback_attempts_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "octet_length(source_digest) = 32",
            name=op.f("ck_login_callback_attempts_source_digest_length"),
        ),
        sa.CheckConstraint(
            "succeeded_at IS NULL OR succeeded_at >= started_at",
            name=op.f("ck_login_callback_attempts_valid_success_time"),
        ),
        sa.CheckConstraint(
            "(succeeded_at IS NULL) = (account_id IS NULL)",
            name=op.f("ck_login_callback_attempts_success_identifies_account"),
        ),
    )
    op.create_index(
        "ix_login_callback_attempts_source_time",
        "login_callback_attempts",
        ["source_digest", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_login_callback_attempts_source_time", table_name="login_callback_attempts")
    op.drop_table("login_callback_attempts")
