"""Bound actual participant thread lists and human activity lookups."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_conversation_list_indexes"
down_revision: str | Sequence[str] | None = "0034_operator_inspection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_conversations_low_participant", "conversations", ["low_id", "id"])
    op.create_index("ix_conversations_high_participant", "conversations", ["high_id", "id"])
    op.create_index(
        "ix_messages_conversation_activity",
        "messages",
        ["conversation_id", sa.text("sent_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_activity", table_name="messages")
    op.drop_index("ix_conversations_high_participant", table_name="conversations")
    op.drop_index("ix_conversations_low_participant", table_name="conversations")
