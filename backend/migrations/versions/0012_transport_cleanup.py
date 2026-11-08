"""Recoverable transport-only object cleanup; retained business files are excluded."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_transport_cleanup"
down_revision: str | Sequence[str] | None = "0011_photo_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "photo_transport_cleanup",
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleaned_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("upload_id", name="pk_photo_transport_cleanup"),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["photo_uploads.id"],
            name="fk_photo_transport_cleanup_upload_id_photo_uploads",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "attempts >= 0", name=op.f("ck_photo_transport_cleanup_nonnegative_attempts")
        ),
        sa.CheckConstraint(
            "(generation IS NULL) = (lease_until IS NULL)",
            name=op.f("ck_photo_transport_cleanup_paired_lease"),
        ),
        sa.CheckConstraint(
            "cleaned_at IS NULL OR lease_until IS NULL",
            name=op.f("ck_photo_transport_cleanup_finished_lease_released"),
        ),
    )
    op.create_index(
        "ix_photo_transport_cleanup_pending",
        "photo_transport_cleanup",
        ["next_attempt_at", "upload_id"],
        postgresql_where=sa.text("cleaned_at IS NULL"),
    )
    op.execute(
        "INSERT INTO photo_transport_cleanup (upload_id, attempts, next_attempt_at) "
        "SELECT id, 0, upload_expires_at FROM photo_uploads"
    )


def downgrade() -> None:
    op.drop_table("photo_transport_cleanup")
