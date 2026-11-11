"""Recipient-owned committed change delivery index, without copied private payloads."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_change_delivery"
down_revision: str | Sequence[str] | None = "0035_conversation_list_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "change_recipient_heads",
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("next_sequence", sa.BigInteger(), nullable=False),
        sa.Column("expired_through_sequence", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "expired_through_sequence >= 0 AND expired_through_sequence < next_sequence",
            name=op.f("ck_change_recipient_heads_retained_floor"),
        ),
        sa.CheckConstraint(
            "next_sequence > 0", name=op.f("ck_change_recipient_heads_positive_next_sequence")
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["accounts.id"],
            name=op.f("fk_change_recipient_heads_recipient_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("recipient_id", name=op.f("pk_change_recipient_heads")),
    )
    op.create_table(
        "change_outbox",
        sa.Column("canonical_event_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("staged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_sequence", sa.BigInteger(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(published_sequence IS NULL AND published_at IS NULL) OR "
            "(published_sequence IS NOT NULL AND published_sequence > 0 AND "
            "published_at IS NOT NULL)",
            name=op.f("ck_change_outbox_paired_publication"),
        ),
        sa.ForeignKeyConstraint(
            ["canonical_event_id"],
            ["product_events.id"],
            name=op.f("fk_change_outbox_canonical_event_id_product_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["accounts.id"],
            name=op.f("fk_change_outbox_recipient_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "canonical_event_id", "recipient_id", name=op.f("pk_change_outbox")
        ),
        sa.UniqueConstraint(
            "recipient_id", "published_sequence", name="uq_change_outbox_recipient_sequence"
        ),
    )
    op.create_index(
        "ix_change_outbox_due",
        "change_outbox",
        ["staged_at", "canonical_event_id", "recipient_id"],
        unique=False,
        postgresql_where=sa.text("published_sequence IS NULL"),
    )
    op.create_table(
        "published_changes",
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("canonical_event_id", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence > 0", name=op.f("ck_published_changes_positive_sequence")),
        sa.ForeignKeyConstraint(
            ["canonical_event_id", "recipient_id"],
            ["change_outbox.canonical_event_id", "change_outbox.recipient_id"],
            name="fk_published_changes_actual_staged_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["change_recipient_heads.recipient_id"],
            name=op.f("fk_published_changes_recipient_id_change_recipient_heads"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("recipient_id", "sequence", name=op.f("pk_published_changes")),
        sa.UniqueConstraint(
            "canonical_event_id", "recipient_id", name="uq_published_changes_source_recipient"
        ),
    )
    op.create_index(
        "ix_published_changes_retention",
        "published_changes",
        ["published_at", "recipient_id", "sequence"],
        unique=False,
    )


def downgrade() -> None:
    retained = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM change_outbox) OR EXISTS (SELECT 1 FROM "
                "change_recipient_heads)"
            )
        )
        .scalar_one()
    )
    if retained:
        raise RuntimeError("Cannot remove pending or published change delivery history")
    op.drop_index("ix_published_changes_retention", table_name="published_changes")
    op.drop_table("published_changes")
    op.drop_index(
        "ix_change_outbox_due",
        table_name="change_outbox",
        postgresql_where=sa.text("published_sequence IS NULL"),
    )
    op.drop_table("change_outbox")
    op.drop_table("change_recipient_heads")
