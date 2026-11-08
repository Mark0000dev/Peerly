"""Core identity, sessions and nontransferable institutional bindings.

Revision ID: 0001_identity
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_identity"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
    )
    op.create_table(
        "external_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_external_identities"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            ondelete="RESTRICT",
            name="fk_external_identities_account_id_accounts",
        ),
        sa.UniqueConstraint("issuer", "subject", name="uq_external_identities_issuer_subject"),
        sa.UniqueConstraint("account_id", name="uq_external_identities_account_id"),
        sa.CheckConstraint(
            "issuer = 'https://accounts.google.com'", name="ck_external_identities_google_issuer"
        ),
        sa.CheckConstraint("length(subject) > 0", name="ck_external_identities_nonempty_subject"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("secret_digest", sa.LargeBinary(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            ondelete="RESTRICT",
            name="fk_sessions_account_id_accounts",
        ),
        sa.UniqueConstraint("secret_digest", name="uq_sessions_secret_digest"),
        sa.UniqueConstraint("id", "account_id", name="uq_sessions_id_account_id"),
        sa.CheckConstraint(
            "octet_length(secret_digest) = 32", name="ck_sessions_secret_digest_length"
        ),
        sa.CheckConstraint("expires_at > issued_at", name="ck_sessions_expiry_after_issuance"),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at", name="ck_sessions_valid_revocation"
        ),
    )
    op.create_index("ix_sessions_account_id", "sessions", ["account_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_table(
        "institutional_bindings",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("account_id", name="pk_institutional_bindings"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            ondelete="RESTRICT",
            name="fk_institutional_bindings_account_id_accounts",
        ),
        sa.UniqueConstraint("email", name="uq_institutional_bindings_email"),
        sa.CheckConstraint(
            "email = lower(btrim(email)) AND "
            "email ~ '^[a-z0-9!#$%&''*+/=?^_`{|}~-]+"
            "(\\.[a-z0-9!#$%&''*+/=?^_`{|}~-]+)*@mail\\.apu\\.edu\\.my$' "
            "AND length(split_part(email, '@', 1)) <= 64",
            name="ck_institutional_bindings_canonical_student_email",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= verified_at",
            name="ck_institutional_bindings_valid_revocation",
        ),
    )


def downgrade() -> None:
    op.drop_table("institutional_bindings")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_account_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("external_identities")
    op.drop_table("accounts")
