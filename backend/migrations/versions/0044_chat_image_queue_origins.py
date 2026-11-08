"""Actual first queued image revision correlation, without retrospective attribution."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_chat_image_queue_origins"
down_revision: str | Sequence[str] | None = "0043_operator_profile_media"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_image_queue_origins",
        sa.Column("image_id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(32), nullable=True),
        sa.Column("span_id", sa.String(16), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id", "conversation_id", "client_message_id", "image_id", "version", "state"],
            [
                "chat_image_revisions.account_id",
                "chat_image_revisions.conversation_id",
                "chat_image_revisions.client_message_id",
                "chat_image_revisions.image_id",
                "chat_image_revisions.version",
                "chat_image_revisions.state",
            ],
            name="fk_chat_image_queue_origin_owned_revision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("state='queued' AND version>0", name="actual_queued_revision"),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR "
            "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
            "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0',32) AND "
            "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0',16))",
            name="origin_trace_pair",
        ),
    )


def downgrade() -> None:
    retained = op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM chat_image_queue_origins)")
    )
    if retained:
        raise RuntimeError("Refusing to drop retained image queue execution origins")
    op.drop_table("chat_image_queue_origins")
