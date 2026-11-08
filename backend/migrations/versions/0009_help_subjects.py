"""Immutable help selections, empty saved state and original retry results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_help_subjects"
down_revision: str | Sequence[str] | None = "0008_catalogue_goals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "help_revisions",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "version", name="pk_help_revisions"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_help_revisions_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_help_revisions_positive_version")),
    )
    op.create_table(
        "help_profiles",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("account_id", name="pk_help_profiles"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_help_profiles_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "current_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            name="fk_help_profiles_account_id_help_revisions",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("current_version > 0", name=op.f("ck_help_profiles_positive_version")),
    )
    op.create_table(
        "help_selections",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("subject_label", sa.String(80), nullable=False),
        sa.Column("topic_note", sa.String(80), nullable=True),
        sa.PrimaryKeyConstraint("account_id", "version", "slot", name="pk_help_selections"),
        sa.ForeignKeyConstraint(
            ["account_id", "version"],
            ["help_revisions.account_id", "help_revisions.version"],
            name="fk_help_selections_account_id_help_revisions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_help_selections_subject_id_subjects",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "account_id", "version", "subject_id", name="uq_help_selections_subject"
        ),
        sa.CheckConstraint("slot BETWEEN 0 AND 4", name=op.f("ck_help_selections_bounded_slot")),
        sa.CheckConstraint(
            "length(subject_label) BETWEEN 1 AND 80",
            name=op.f("ck_help_selections_subject_label_length"),
        ),
        sa.CheckConstraint(
            "topic_note IS NULL OR length(topic_note) BETWEEN 1 AND 80",
            name=op.f("ck_help_selections_topic_note_length"),
        ),
    )
    op.create_table(
        "help_write_intents",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "key", name="pk_help_write_intents"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_help_write_intents_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "result_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            name="fk_help_write_intents_account_id_help_revisions",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'", name=op.f("ck_help_write_intents_intent_key_shape")
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32", name=op.f("ck_help_write_intents_fingerprint_length")
        ),
    )


def downgrade() -> None:
    op.drop_table("help_write_intents")
    op.drop_table("help_selections")
    op.drop_table("help_profiles")
    op.drop_table("help_revisions")
