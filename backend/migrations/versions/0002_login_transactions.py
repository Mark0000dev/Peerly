"""Browser-bound, one-use OIDC transactions with encrypted verifier material."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_login_transactions"
down_revision: str | Sequence[str] | None = "0001_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state_digest", sa.LargeBinary(), nullable=False),
        sa.Column("browser_digest", sa.LargeBinary(), nullable=False),
        sa.Column("source_digest", sa.LargeBinary(), nullable=False),
        sa.Column("sealed_material", sa.LargeBinary(), nullable=True),
        sa.Column("return_to", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_login_transactions"),
        sa.UniqueConstraint("state_digest", name="uq_login_transactions_state_digest"),
        sa.CheckConstraint(
            "octet_length(state_digest) = 32 AND octet_length(browser_digest) = 32 "
            "AND octet_length(source_digest) = 32",
            name="ck_login_transactions_digest_lengths",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_login_transactions_valid_expiry"),
        sa.CheckConstraint(
            "return_to IN ('/', '/onboarding')", name="ck_login_transactions_local_return_route"
        ),
        sa.CheckConstraint(
            "(consumed_at IS NULL AND sealed_material IS NOT NULL) OR "
            "(consumed_at IS NOT NULL AND sealed_material IS NULL)",
            name="ck_login_transactions_consumed_erases_material",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR (consumed_at IS NOT NULL AND completed_at >= consumed_at)",
            name="ck_login_transactions_completion_after_consumption",
        ),
    )
    op.create_index(
        "ix_login_transactions_browser_digest", "login_transactions", ["browser_digest"]
    )
    op.create_index("ix_login_transactions_source_digest", "login_transactions", ["source_digest"])
    op.create_index("ix_login_transactions_created_at", "login_transactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_login_transactions_created_at", table_name="login_transactions")
    op.drop_index("ix_login_transactions_source_digest", table_name="login_transactions")
    op.drop_index("ix_login_transactions_browser_digest", table_name="login_transactions")
    op.drop_table("login_transactions")
