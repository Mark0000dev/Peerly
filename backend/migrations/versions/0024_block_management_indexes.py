"""Bound owner block management and the last known disclosure lookup."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_block_management_indexes"
down_revision: str | Sequence[str] | None = "0023_profile_access_origin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_blocks_owner_relationship", "blocks", ["blocker_id", "relationship_id"])
    op.create_index(
        "ix_block_write_intents_owner_target_context",
        "block_write_intents",
        ["actor_id", "target_id", "created_at", "key"],
        postgresql_where=sa.text("context_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_block_write_intents_owner_target_context", table_name="block_write_intents")
    op.drop_index("ix_blocks_owner_relationship", table_name="blocks")
