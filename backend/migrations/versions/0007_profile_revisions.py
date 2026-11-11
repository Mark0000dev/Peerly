"""Owned saved profile revisions, immutable language selections and retry results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_profile_revisions"
down_revision: str | Sequence[str] | None = "0006_email_origin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profile_revisions",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(50), nullable=True),
        sa.Column("about", sa.String(160), nullable=True),
        sa.Column("programme", sa.String(80), nullable=True),
        sa.Column("year_label", sa.String(32), nullable=True),
        sa.Column("task", sa.String(16), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "version", name="pk_profile_revisions"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_profile_revisions_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_profile_revisions_positive_version")),
        sa.CheckConstraint(
            "display_name IS NULL OR length(display_name) BETWEEN 2 AND 50",
            name=op.f("ck_profile_revisions_display_name_length"),
        ),
        sa.CheckConstraint(
            "about IS NULL OR length(about) BETWEEN 1 AND 160",
            name=op.f("ck_profile_revisions_about_length"),
        ),
        sa.CheckConstraint(
            "programme IS NULL OR length(programme) BETWEEN 1 AND 80",
            name=op.f("ck_profile_revisions_programme_length"),
        ),
        sa.CheckConstraint(
            "year_label IS NULL OR length(year_label) BETWEEN 1 AND 32",
            name=op.f("ck_profile_revisions_year_label_length"),
        ),
        sa.CheckConstraint(
            "task IN ('find_help', 'offer_help')", name=op.f("ck_profile_revisions_known_task")
        ),
    )
    op.create_table(
        "profiles",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("account_id", name="pk_profiles"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_profiles_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "current_version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            name="fk_profiles_account_id_profile_revisions",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("current_version > 0", name=op.f("ck_profiles_positive_version")),
    )
    op.create_table(
        "profile_languages",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(35), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "version", "slot", name="pk_profile_languages"),
        sa.ForeignKeyConstraint(
            ["account_id", "version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            name="fk_profile_languages_account_id_profile_revisions",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("account_id", "version", "code", name="uq_profile_languages_selection"),
        sa.CheckConstraint("slot BETWEEN 0 AND 4", name=op.f("ck_profile_languages_bounded_slot")),
        sa.CheckConstraint(
            "code ~ '^[a-z]{2,3}(-[a-z0-9]{2,8})*$'",
            name=op.f("ck_profile_languages_selection_shape"),
        ),
    )
    op.create_table(
        "profile_write_intents",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "key", name="pk_profile_write_intents"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_profile_write_intents_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "result_version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            name="fk_profile_write_intents_account_id_profile_revisions",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'", name=op.f("ck_profile_write_intents_intent_key_shape")
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32",
            name=op.f("ck_profile_write_intents_fingerprint_length"),
        ),
    )


def downgrade() -> None:
    op.drop_table("profile_write_intents")
    op.drop_table("profile_languages")
    op.drop_table("profiles")
    op.drop_table("profile_revisions")
