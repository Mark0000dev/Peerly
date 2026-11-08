"""Confirmed images bind the exact owned Ready revision and processing rendition."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_confirmed_message_images"
down_revision: str | Sequence[str] | None = "0046_lifecycle_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_chat_image_revision_rendition",
        "chat_image_revisions",
        ["image_id", "version", "attempt_id", "state"],
    )
    op.add_column("messages", sa.Column("image_id", sa.Uuid(), nullable=True))
    op.add_column("messages", sa.Column("image_version", sa.Integer(), nullable=True))
    op.add_column("messages", sa.Column("image_attempt_id", sa.Uuid(), nullable=True))
    op.add_column("messages", sa.Column("image_state", sa.String(16), nullable=True))
    op.alter_column("messages", "text", existing_type=sa.String(2000), nullable=True)
    op.drop_constraint(op.f("ck_messages_nonblank_bounded_text"), "messages", type_="check")
    op.create_check_constraint(
        op.f("ck_messages_nonblank_bounded_text"),
        "messages",
        "text IS NULL OR (length(text) BETWEEN 1 AND 2000 AND text ~ '[^[:space:]]')",
    )
    op.create_check_constraint(
        op.f("ck_messages_content_required"), "messages", "text IS NOT NULL OR image_id IS NOT NULL"
    )
    op.create_check_constraint(
        op.f("ck_messages_image_source_shape"),
        "messages",
        "(image_id IS NULL AND image_version IS NULL AND "
        "image_attempt_id IS NULL AND image_state IS NULL) OR "
        "(image_id IS NOT NULL AND image_version IS NOT NULL AND image_version>0 AND "
        "image_attempt_id IS NOT NULL AND image_state IS NOT NULL AND image_state='ready')",
    )
    op.create_foreign_key(
        "fk_messages_owned_ready_image",
        "messages",
        "chat_image_revisions",
        [
            "author_id",
            "conversation_id",
            "client_message_id",
            "image_id",
            "image_version",
            "image_state",
        ],
        ["account_id", "conversation_id", "client_message_id", "image_id", "version", "state"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_messages_actual_image_rendition",
        "messages",
        "chat_image_revisions",
        ["image_id", "image_version", "image_attempt_id", "image_state"],
        ["image_id", "version", "attempt_id", "state"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    retained = op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM messages WHERE image_id IS NOT NULL OR text IS NULL)")
    )
    if retained:
        raise RuntimeError("Refusing to drop retained confirmed image messages")
    op.drop_constraint("fk_messages_actual_image_rendition", "messages", type_="foreignkey")
    op.drop_constraint("fk_messages_owned_ready_image", "messages", type_="foreignkey")
    op.drop_constraint(op.f("ck_messages_image_source_shape"), "messages", type_="check")
    op.drop_constraint(op.f("ck_messages_content_required"), "messages", type_="check")
    op.drop_constraint(op.f("ck_messages_nonblank_bounded_text"), "messages", type_="check")
    op.create_check_constraint(
        op.f("ck_messages_nonblank_bounded_text"),
        "messages",
        "length(text) BETWEEN 1 AND 2000 AND text ~ '[^[:space:]]'",
    )
    op.alter_column("messages", "text", existing_type=sa.String(2000), nullable=False)
    op.drop_column("messages", "image_state")
    op.drop_column("messages", "image_attempt_id")
    op.drop_column("messages", "image_version")
    op.drop_column("messages", "image_id")
    op.drop_constraint("uq_chat_image_revision_rendition", "chat_image_revisions", type_="unique")
