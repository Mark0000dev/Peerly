"""Leased deletion of expired image transport objects, never retained business media."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_chat_image_cleanup"
down_revision: str | Sequence[str] | None = "0047_confirmed_message_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_image_transport_cleanup",
        sa.Column("image_id", sa.Uuid(), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleaned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["chat_image_preparations.id"],
            name="fk_chat_image_cleanup_owned_source",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("attempts>=0", name="nonnegative_attempts"),
        sa.CheckConstraint("(generation IS NULL)=(lease_until IS NULL)", name="paired_lease"),
        sa.CheckConstraint(
            "cleaned_at IS NULL OR lease_until IS NULL", name="finished_lease_released"
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO chat_image_transport_cleanup (image_id,attempts,next_attempt_at) "
            "SELECT id,0,upload_expires_at FROM chat_image_preparations"
        )
    )
    op.create_index(
        "ix_chat_image_transport_cleanup_pending",
        "chat_image_transport_cleanup",
        ["next_attempt_at", "image_id"],
        postgresql_where=sa.text("cleaned_at IS NULL"),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM chat_image_transport_cleanup)")):
        raise RuntimeError("Refusing to drop retained chat image transport cleanup metadata")
    op.drop_index(
        "ix_chat_image_transport_cleanup_pending", table_name="chat_image_transport_cleanup"
    )
    op.drop_table("chat_image_transport_cleanup")
