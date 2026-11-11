"""Retain deleted associations while uniquely claiming only active identities."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_identity_recreation"
down_revision: str | Sequence[str] | None = "0053_operator_support_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_accounts_id_deleted_at", "accounts", ["id", "deleted_at"])
    for table, constraint in (
        ("external_identities", "fk_external_identities_retired_account"),
        ("institutional_bindings", "fk_institutional_bindings_retired_account"),
    ):
        op.add_column(table, sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
        op.create_foreign_key(
            constraint,
            table,
            "accounts",
            ["account_id", "retired_at"],
            ["id", "deleted_at"],
            ondelete="RESTRICT",
        )
    op.execute(
        sa.text(
            "UPDATE external_identities AS identity SET retired_at=account.deleted_at "
            "FROM accounts AS account WHERE identity.account_id=account.id "
            "AND account.deleted_at IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE institutional_bindings AS binding SET retired_at=account.deleted_at "
            "FROM accounts AS account WHERE binding.account_id=account.id "
            "AND account.deleted_at IS NOT NULL"
        )
    )
    op.drop_constraint(
        "uq_external_identities_issuer_subject", "external_identities", type_="unique"
    )
    op.drop_constraint("uq_institutional_bindings_email", "institutional_bindings", type_="unique")
    op.create_index(
        "uq_external_identities_active_issuer_subject",
        "external_identities",
        ["issuer", "subject"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_index(
        "uq_institutional_bindings_active_email",
        "institutional_bindings",
        ["email"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_index(
        "ix_external_identities_issuer_subject_history",
        "external_identities",
        ["issuer", "subject"],
    )
    op.create_index("ix_institutional_bindings_email_history", "institutional_bindings", ["email"])


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM external_identities WHERE retired_at IS NOT NULL) "
            "OR EXISTS(SELECT 1 FROM institutional_bindings WHERE retired_at IS NOT NULL)"
        )
    ):
        raise RuntimeError("Refusing to discard retained identity retirement sources")
    op.drop_index("ix_institutional_bindings_email_history", table_name="institutional_bindings")
    op.drop_index("ix_external_identities_issuer_subject_history", table_name="external_identities")
    op.drop_index("uq_institutional_bindings_active_email", table_name="institutional_bindings")
    op.drop_index("uq_external_identities_active_issuer_subject", table_name="external_identities")
    op.create_unique_constraint(
        "uq_external_identities_issuer_subject", "external_identities", ["issuer", "subject"]
    )
    op.create_unique_constraint(
        "uq_institutional_bindings_email", "institutional_bindings", ["email"]
    )
    op.drop_constraint(
        "fk_institutional_bindings_retired_account", "institutional_bindings", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_external_identities_retired_account", "external_identities", type_="foreignkey"
    )
    op.drop_column("institutional_bindings", "retired_at")
    op.drop_column("external_identities", "retired_at")
    op.drop_constraint("uq_accounts_id_deleted_at", "accounts", type_="unique")
