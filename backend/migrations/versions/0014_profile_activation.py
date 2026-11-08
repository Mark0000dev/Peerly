"""Explicit readiness activation and immutable visibility history; no inferred backfill."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_profile_activation"
down_revision: str | Sequence[str] | None = "0013_profile_languages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_registration_receipts_owner_id", "registration_receipts", ["account_id", "id"]
    )
    op.create_table(
        "profile_activations",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("registration_id", sa.Uuid(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("photo_version", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=True),
        sa.Column("goal_version", sa.Integer(), nullable=True),
        sa.Column("help_version", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visibility_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("account_id"),
        sa.ForeignKeyConstraint(["account_id"], ["profiles.account_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["account_id", "registration_id"],
            ["registration_receipts.account_id", "registration_receipts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "profile_version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "photo_version"],
            ["photo_revisions.account_id", "photo_revisions.version"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "goal_id", "goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "help_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "profile_version > 0 AND photo_version > 0 AND visibility_version > 0",
            name="positive_versions",
        ),
        sa.CheckConstraint(
            "(goal_id IS NULL AND goal_version IS NULL) OR "
            "(goal_id IS NOT NULL AND goal_version IS NOT NULL AND goal_version > 0)",
            name="paired_goal_revision",
        ),
        sa.CheckConstraint(
            "help_version IS NULL OR help_version > 0", name="positive_help_version"
        ),
        sa.CheckConstraint("goal_id IS NOT NULL OR help_version IS NOT NULL", name="study_context"),
    )
    op.create_table(
        "visibility_revisions",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "version"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["profile_activations.account_id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("version > 0", name="positive_version"),
        sa.CheckConstraint("changed_at >= completed_at", name="after_completion"),
        sa.CheckConstraint(
            "hidden_at IS NULL OR (hidden_at >= completed_at AND hidden_at <= changed_at)",
            name="ordered_hidden_time",
        ),
    )
    op.create_foreign_key(
        "fk_profile_activations_visibility",
        "profile_activations",
        "visibility_revisions",
        ["account_id", "visibility_version"],
        ["account_id", "version"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "visibility_write_intents",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "key"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["account_id", "result_version"],
            ["visibility_revisions.account_id", "visibility_revisions.version"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        sa.CheckConstraint("octet_length(fingerprint) = 32", name="fingerprint_length"),
    )


def downgrade() -> None:
    op.drop_table("visibility_write_intents")
    op.drop_constraint(
        "fk_profile_activations_visibility", "profile_activations", type_="foreignkey"
    )
    op.drop_table("visibility_revisions")
    op.drop_table("profile_activations")
    op.drop_constraint("uq_registration_receipts_owner_id", "registration_receipts", type_="unique")
