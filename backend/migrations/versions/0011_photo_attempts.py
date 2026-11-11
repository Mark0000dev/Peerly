"""Durable bounded photo processing attempts and generation references."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_photo_attempts"
down_revision: str | Sequence[str] | None = "0010_photo_uploads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "photo_processing_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("failure", sa.String(32), nullable=True),
        sa.Column("display_width", sa.Integer(), nullable=True),
        sa.Column("display_height", sa.Integer(), nullable=True),
        sa.Column("display_size", sa.Integer(), nullable=True),
        sa.Column("display_digest", sa.LargeBinary(), nullable=True),
        sa.CheckConstraint(
            "number BETWEEN 1 AND 3", name=op.f("ck_photo_processing_attempts_bounded_number")
        ),
        sa.CheckConstraint(
            "(display_size IS NULL AND display_width IS NULL AND display_height IS "
            "NULL AND display_digest IS NULL) OR (display_size IS NOT NULL AND "
            "display_width IS NOT NULL AND display_height IS NOT NULL AND "
            "display_digest IS NOT NULL AND display_size > 0 AND display_width "
            "BETWEEN 1 AND 1024 AND display_height BETWEEN 1 AND 1024 AND "
            "octet_length(display_digest) = 32)",
            name=op.f("ck_photo_processing_attempts_complete_display_metadata"),
        ),
        sa.CheckConstraint(
            "(outcome = 'processing') = (finished_at IS NULL)",
            name=op.f("ck_photo_processing_attempts_finish_required"),
        ),
        sa.CheckConstraint(
            "failure IS NULL OR failure IN ('invalid_image', 'unsupported_format', "
            "'too_large', 'dimensions_exceeded', 'animated_image', "
            "'content_changed', 'photo_changed', 'account_unavailable', "
            "'storage_unavailable', 'processing_unavailable')",
            name=op.f("ck_photo_processing_attempts_known_failure"),
        ),
        sa.CheckConstraint(
            "outcome IN ('processing', 'ready', 'retry', 'rejected', 'stale', 'interrupted')",
            name=op.f("ck_photo_processing_attempts_known_outcome"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_photo_processing_attempts_ordered_finish"),
        ),
        sa.CheckConstraint(
            "lease_until > started_at", name=op.f("ck_photo_processing_attempts_ordered_lease")
        ),
        sa.CheckConstraint(
            "next_attempt_at IS NULL OR next_attempt_at > finished_at",
            name=op.f("ck_photo_processing_attempts_ordered_retry"),
        ),
        sa.CheckConstraint(
            "outcome <> 'ready' OR display_digest IS NOT NULL",
            name=op.f("ck_photo_processing_attempts_ready_metadata"),
        ),
        sa.CheckConstraint(
            "(outcome = 'retry') = (next_attempt_at IS NOT NULL)",
            name=op.f("ck_photo_processing_attempts_retry_required"),
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["photo_uploads.id"],
            name=op.f("fk_photo_processing_attempts_upload_id_photo_uploads"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photo_processing_attempts")),
        sa.UniqueConstraint(
            "upload_id", "number", name=op.f("uq_photo_processing_attempts_number")
        ),
        sa.UniqueConstraint("upload_id", "id", name=op.f("uq_photo_processing_attempts_upload_id")),
    )
    op.create_foreign_key(
        "fk_photo_upload_revisions_attempt",
        "photo_upload_revisions",
        "photo_processing_attempts",
        ["upload_id", "attempt_id"],
        ["upload_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_photo_upload_revisions_known_failure"), "photo_upload_revisions", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_photo_upload_revisions_known_failure"),
        "photo_upload_revisions",
        "failure IS NULL OR failure IN ('invalid_image', 'unsupported_format', "
        "'too_large', 'dimensions_exceeded', 'animated_image', "
        "'content_changed', 'photo_changed', 'account_unavailable', "
        "'storage_unavailable', 'processing_unavailable')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_photo_upload_revisions_attempt", "photo_upload_revisions", type_="foreignkey"
    )
    op.drop_table("photo_processing_attempts")
    op.drop_constraint(
        op.f("ck_photo_upload_revisions_known_failure"), "photo_upload_revisions", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_photo_upload_revisions_known_failure"),
        "photo_upload_revisions",
        "failure IS NULL OR failure IN ('invalid_image', 'unsupported_format', "
        "'too_large', 'dimensions_exceeded', 'animated_image', "
        "'content_changed', 'photo_changed', 'account_unavailable', "
        "'storage_unavailable')",
    )
