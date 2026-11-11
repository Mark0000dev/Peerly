"""Canonical pairs and retained directional block history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_directional_blocks"
down_revision: str | Sequence[str] | None = "0020_profile_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("low_id < high_id", name=op.f("ck_relationships_canonical_pair")),
        sa.ForeignKeyConstraint(
            ["high_id"],
            ["accounts.id"],
            name=op.f("fk_relationships_high_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["low_id"],
            ["accounts.id"],
            name=op.f("fk_relationships_low_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_relationships")),
        sa.UniqueConstraint("id", "low_id", "high_id", name="uq_relationships_participants"),
        sa.UniqueConstraint("low_id", "high_id", name="uq_relationships_pair"),
    )
    op.create_table(
        "block_revisions",
        sa.Column("relationship_id", sa.Uuid(), nullable=False),
        sa.Column("blocker_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(blocker_id = low_id AND target_id = high_id) OR "
            " (blocker_id = high_id AND target_id = low_id)",
            name=op.f("ck_block_revisions_directional_participants"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_block_revisions_positive_version")),
        sa.ForeignKeyConstraint(
            ["relationship_id", "low_id", "high_id"],
            ["relationships.id", "relationships.low_id", "relationships.high_id"],
            name=op.f("fk_block_revisions_relationship_id_relationships"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "relationship_id", "blocker_id", "version", name=op.f("pk_block_revisions")
        ),
        sa.UniqueConstraint(
            "relationship_id",
            "blocker_id",
            "version",
            "target_id",
            name="uq_block_revisions_target",
        ),
    )
    op.create_table(
        "blocks",
        sa.Column("relationship_id", sa.Uuid(), nullable=False),
        sa.Column("blocker_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("current_version > 0", name=op.f("ck_blocks_positive_version")),
        sa.ForeignKeyConstraint(
            ["relationship_id", "blocker_id", "current_version"],
            [
                "block_revisions.relationship_id",
                "block_revisions.blocker_id",
                "block_revisions.version",
            ],
            name=op.f("fk_blocks_relationship_id_block_revisions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("relationship_id", "blocker_id", name=op.f("pk_blocks")),
    )
    op.create_table(
        "block_write_intents",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_id", sa.Uuid(), nullable=True),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("context_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'", name=op.f("ck_block_write_intents_intent_key_shape")
        ),
        sa.CheckConstraint(
            "(result_version = 0 AND relationship_id IS NULL) OR "
            " (result_version > 0 AND relationship_id IS NOT NULL)",
            name=op.f("ck_block_write_intents_result_shape"),
        ),
        sa.CheckConstraint(
            "actor_id != target_id", name=op.f("ck_block_write_intents_distinct_participants")
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32", name=op.f("ck_block_write_intents_fingerprint_length")
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_block_write_intents_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["context_id", "actor_id"],
            ["profile_access_contexts.id", "profile_access_contexts.viewer_id"],
            name=op.f("fk_block_write_intents_context_id_profile_access_contexts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["relationship_id", "actor_id", "result_version", "target_id"],
            [
                "block_revisions.relationship_id",
                "block_revisions.blocker_id",
                "block_revisions.version",
                "block_revisions.target_id",
            ],
            name=op.f("fk_block_write_intents_relationship_id_block_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["accounts.id"],
            name=op.f("fk_block_write_intents_target_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("actor_id", "key", name=op.f("pk_block_write_intents")),
    )


def downgrade() -> None:
    retained = op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM relationships)"))
    if retained:
        raise RuntimeError("Cannot downgrade retained relationship history")
    op.drop_table("block_write_intents")
    op.drop_table("blocks")
    op.drop_table("block_revisions")
    op.drop_table("relationships")
