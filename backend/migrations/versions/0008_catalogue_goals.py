"""Authored subject catalogue and owned immutable goal revisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_catalogue_goals"
down_revision: str | Sequence[str] | None = "0007_profile_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("normalized_name", sa.String(240), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_subjects"),
        sa.UniqueConstraint("normalized_name", name="uq_subjects_normalized_name"),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 80 AND length(btrim(name)) > 0",
            name=op.f("ck_subjects_name_length"),
        ),
        sa.CheckConstraint(
            "length(normalized_name) BETWEEN 1 AND 240", name=op.f("ck_subjects_normalized_length")
        ),
        sa.CheckConstraint(
            "archived_at IS NULL OR archived_at >= created_at",
            name=op.f("ck_subjects_valid_archival"),
        ),
    )
    op.create_table(
        "subject_aliases",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("normalized_alias", sa.String(240), nullable=False),
        sa.PrimaryKeyConstraint("subject_id", "slot", name="pk_subject_aliases"),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_subject_aliases_subject_id_subjects",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("subject_id", "normalized_alias", name="uq_subject_aliases_normalized"),
        sa.CheckConstraint("slot BETWEEN 0 AND 19", name=op.f("ck_subject_aliases_bounded_slot")),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 80 AND length(btrim(name)) > 0",
            name=op.f("ck_subject_aliases_name_length"),
        ),
        sa.CheckConstraint(
            "length(normalized_alias) BETWEEN 1 AND 240",
            name=op.f("ck_subject_aliases_normalized_length"),
        ),
    )
    op.create_index("ix_subject_aliases_normalized", "subject_aliases", ["normalized_alias"])
    op.create_table(
        "goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_goals"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_goals_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "account_id", name="uq_goals_id_account"),
        sa.CheckConstraint("current_version > 0", name=op.f("ck_goals_positive_version")),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name=op.f("ck_goals_valid_completion"),
        ),
    )
    op.create_index(
        "uq_goals_active_account",
        "goals",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("completed_at IS NULL"),
    )
    op.create_table(
        "goal_revisions",
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("subject_label", sa.String(80), nullable=False),
        sa.Column("topic", sa.String(80), nullable=True),
        sa.Column("context", sa.String(240), nullable=True),
        sa.Column("shared_learning", sa.Boolean(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("goal_id", "version", name="pk_goal_revisions"),
        sa.ForeignKeyConstraint(
            ["goal_id", "account_id"],
            ["goals.id", "goals.account_id"],
            name="fk_goal_revisions_goal_id_goals",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_goal_revisions_subject_id_subjects",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "account_id", "goal_id", "version", name="uq_goal_revisions_owner_version"
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_goal_revisions_positive_version")),
        sa.CheckConstraint(
            "length(subject_label) BETWEEN 1 AND 80",
            name=op.f("ck_goal_revisions_subject_label_length"),
        ),
        sa.CheckConstraint(
            "topic IS NULL OR length(topic) BETWEEN 1 AND 80",
            name=op.f("ck_goal_revisions_topic_length"),
        ),
        sa.CheckConstraint(
            "context IS NULL OR length(context) BETWEEN 1 AND 240",
            name=op.f("ck_goal_revisions_context_length"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at = saved_at",
            name=op.f("ck_goal_revisions_final_revision_time"),
        ),
    )
    op.create_foreign_key(
        "fk_goals_current_revision",
        "goals",
        "goal_revisions",
        ["id", "current_version"],
        ["goal_id", "version"],
        deferrable=True,
        initially="DEFERRED",
        ondelete="RESTRICT",
    )
    op.create_table(
        "goal_write_intents",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "key", name="pk_goal_write_intents"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_goal_write_intents_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "goal_id", "result_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            name="fk_goal_write_intents_account_id_goal_revisions",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'", name=op.f("ck_goal_write_intents_intent_key_shape")
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32", name=op.f("ck_goal_write_intents_fingerprint_length")
        ),
    )


def downgrade() -> None:
    op.drop_table("goal_write_intents")
    op.drop_constraint("fk_goals_current_revision", "goals", type_="foreignkey")
    op.drop_table("goal_revisions")
    op.drop_index("uq_goals_active_account", table_name="goals")
    op.drop_table("goals")
    op.drop_index("ix_subject_aliases_normalized", table_name="subject_aliases")
    op.drop_table("subject_aliases")
    op.drop_table("subjects")
