"""Retained context-bound private passes and actor decision ordering."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_discovery_private_passes"
down_revision: str | Sequence[str] | None = "0024_block_management_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovery_contexts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=True),
        sa.Column("goal_version", sa.Integer(), nullable=True),
        sa.Column("help_version", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(mode IN ('find_help', 'study_together') AND goal_id IS NOT NULL "
            "AND goal_version IS NOT NULL AND goal_version > 0 AND help_version IS NULL) OR "
            "(mode = 'offer_help' AND goal_id IS NULL AND goal_version IS NULL "
            "AND help_version IS NOT NULL AND help_version > 0)",
            name=op.f("ck_discovery_contexts_saved_source_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "goal_id", "goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            name=op.f("fk_discovery_contexts_account_id_goal_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "help_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            name=op.f("fk_discovery_contexts_account_id_help_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_discovery_contexts_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discovery_contexts")),
        sa.UniqueConstraint("id", "account_id", name="uq_discovery_context_owner"),
    )
    op.create_index(
        "uq_discovery_context_goal",
        "discovery_contexts",
        ["account_id", "mode", "goal_id", "goal_version"],
        unique=True,
        postgresql_where=sa.text("goal_id IS NOT NULL"),
    )
    op.create_index(
        "uq_discovery_context_help",
        "discovery_contexts",
        ["account_id", "mode", "help_version"],
        unique=True,
        postgresql_where=sa.text("help_version IS NOT NULL"),
    )
    op.create_table(
        "discovery_decision_heads",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "last_sequence >= 0", name=op.f("ck_discovery_decision_heads_nonnegative_sequence")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_discovery_decision_heads_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("pk_discovery_decision_heads")),
    )
    op.create_table(
        "private_passes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("context_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "account_id <> target_id", name=op.f("ck_private_passes_different_participants")
        ),
        sa.CheckConstraint("current_version > 0", name=op.f("ck_private_passes_positive_version")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_private_passes_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["context_id", "account_id"],
            ["discovery_contexts.id", "discovery_contexts.account_id"],
            name=op.f("fk_private_passes_context_id_discovery_contexts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["accounts.id"],
            name=op.f("fk_private_passes_target_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_private_passes")),
        sa.UniqueConstraint("context_id", "target_id", name="uq_private_pass_context_target"),
        sa.UniqueConstraint("id", "account_id", name="uq_private_pass_owner"),
        sa.UniqueConstraint("id", "context_id", "target_id", name="uq_private_pass_scope"),
    )
    op.create_table(
        "private_pass_revisions",
        sa.Column("pass_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("context_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("decision_sequence", sa.Integer(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision_sequence > 0", name=op.f("ck_private_pass_revisions_positive_sequence")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_private_pass_revisions_positive_version")),
        sa.ForeignKeyConstraint(
            ["pass_id", "account_id"],
            ["private_passes.id", "private_passes.account_id"],
            name="fk_private_pass_revision_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pass_id", "context_id", "target_id"],
            ["private_passes.id", "private_passes.context_id", "private_passes.target_id"],
            name="fk_private_pass_revision_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("pass_id", "version", name=op.f("pk_private_pass_revisions")),
        sa.UniqueConstraint("account_id", "decision_sequence", name="uq_private_pass_decision"),
        sa.UniqueConstraint(
            "pass_id", "version", "account_id", name="uq_private_pass_revision_owner"
        ),
    )
    op.create_table(
        "private_pass_intents",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("pass_id", sa.Uuid(), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'", name=op.f("ck_private_pass_intents_intent_key_shape")
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32",
            name=op.f("ck_private_pass_intents_fingerprint_length"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_private_pass_intents_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pass_id", "result_version", "account_id"],
            [
                "private_pass_revisions.pass_id",
                "private_pass_revisions.version",
                "private_pass_revisions.account_id",
            ],
            name=op.f("fk_private_pass_intents_pass_id_private_pass_revisions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("account_id", "key", name=op.f("pk_private_pass_intents")),
    )
    op.create_foreign_key(
        "fk_private_pass_current_revision",
        "private_passes",
        "private_pass_revisions",
        ["id", "current_version"],
        ["pass_id", "version"],
        ondelete="RESTRICT",
        initially="DEFERRED",
        deferrable=True,
        use_alter=True,
    )


def downgrade() -> None:
    retained = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM discovery_contexts) OR "
                "EXISTS (SELECT 1 FROM discovery_decision_heads WHERE last_sequence > 0)"
            )
        )
        .scalar_one()
    )
    if retained:
        raise RuntimeError("Cannot remove retained private discovery history")
    op.drop_constraint("fk_private_pass_current_revision", "private_passes", type_="foreignkey")
    op.drop_table("private_pass_intents")
    op.drop_table("private_pass_revisions")
    op.drop_table("private_passes")
    op.drop_table("discovery_decision_heads")
    op.drop_table("discovery_contexts")
