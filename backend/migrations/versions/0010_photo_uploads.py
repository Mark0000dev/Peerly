"""Owned immutable photo upload intents, lifecycle revisions and current-photo history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_photo_uploads"
down_revision: str | Sequence[str] | None = "0009_help_subjects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "photo_uploads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("expected_photo_version", sa.Integer(), nullable=False),
        sa.Column("source_size", sa.Integer(), nullable=False),
        sa.Column("source_digest", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_size BETWEEN 1 AND 10000000", name=op.f("ck_photo_uploads_bounded_source")
        ),
        sa.CheckConstraint(
            "octet_length(source_digest) = 32", name=op.f("ck_photo_uploads_digest_length")
        ),
        sa.CheckConstraint(
            "upload_expires_at > created_at AND processing_expires_at >= upload_expires_at",
            name=op.f("ck_photo_uploads_ordered_deadlines"),
        ),
        sa.CheckConstraint(
            "current_version > 0 AND expected_photo_version >= 0",
            name=op.f("ck_photo_uploads_positive_versions"),
        ),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png')",
            name=op.f("ck_photo_uploads_supported_type"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_photo_uploads_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photo_uploads")),
        sa.UniqueConstraint("id", "account_id", name=op.f("uq_photo_uploads_owner")),
    )
    op.create_index(
        "ix_photo_uploads_owner_created",
        "photo_uploads",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "photo_upload_revisions",
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("failure", sa.String(32), nullable=True),
        sa.CheckConstraint(
            "state NOT IN ('processing', 'ready') OR attempt_id IS NOT NULL",
            name=op.f("ck_photo_upload_revisions_attempt_required"),
        ),
        sa.CheckConstraint(
            "(state = 'rejected') = (failure IS NOT NULL)",
            name=op.f("ck_photo_upload_revisions_failure_required"),
        ),
        sa.CheckConstraint(
            "failure IS NULL OR failure IN ('invalid_image', 'unsupported_format', 'too_large', "
            "'dimensions_exceeded', 'animated_image', 'content_changed', 'photo_changed', "
            "'account_unavailable', 'storage_unavailable')",
            name=op.f("ck_photo_upload_revisions_known_failure"),
        ),
        sa.CheckConstraint(
            "state IN ('uploading', 'queued', 'processing', 'ready', "
            "'rejected', 'cancelled', 'expired')",
            name=op.f("ck_photo_upload_revisions_known_state"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_photo_upload_revisions_positive_version")),
        sa.ForeignKeyConstraint(
            ["upload_id", "account_id"],
            ["photo_uploads.id", "photo_uploads.account_id"],
            name=op.f("fk_photo_upload_revisions_upload_id_photo_uploads"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("upload_id", "version", name=op.f("pk_photo_upload_revisions")),
        sa.UniqueConstraint(
            "account_id", "upload_id", "version", name=op.f("uq_photo_upload_revisions_owner")
        ),
        sa.UniqueConstraint(
            "account_id",
            "upload_id",
            "version",
            "state",
            name=op.f("uq_photo_upload_revisions_owner_state"),
        ),
    )
    op.create_index(
        "ix_photo_upload_revisions_state", "photo_upload_revisions", ["state"], unique=False
    )
    op.create_table(
        "photo_revisions",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("upload_version", sa.Integer(), nullable=False),
        sa.Column("upload_state", sa.String(16), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name=op.f("ck_photo_revisions_positive_version")),
        sa.CheckConstraint("upload_state = 'ready'", name=op.f("ck_photo_revisions_ready_upload")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_photo_revisions_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "upload_id", "upload_version", "upload_state"],
            [
                "photo_upload_revisions.account_id",
                "photo_upload_revisions.upload_id",
                "photo_upload_revisions.version",
                "photo_upload_revisions.state",
            ],
            name=op.f("fk_photo_revisions_account_id_photo_upload_revisions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("account_id", "version", name=op.f("pk_photo_revisions")),
    )
    op.create_table(
        "photos",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("current_version > 0", name=op.f("ck_photos_positive_version")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_photos_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "current_version"],
            ["photo_revisions.account_id", "photo_revisions.version"],
            name=op.f("fk_photos_account_id_photo_revisions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("pk_photos")),
    )
    op.create_table(
        "media_write_intents",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32", name=op.f("ck_media_write_intents_fingerprint_length")
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'", name=op.f("ck_media_write_intents_intent_key_shape")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_media_write_intents_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "upload_id", "result_version"],
            [
                "photo_upload_revisions.account_id",
                "photo_upload_revisions.upload_id",
                "photo_upload_revisions.version",
            ],
            name=op.f("fk_media_write_intents_account_id_photo_upload_revisions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("account_id", "key", name=op.f("pk_media_write_intents")),
    )
    op.create_foreign_key(
        "fk_photo_uploads_current_revision",
        "photo_uploads",
        "photo_upload_revisions",
        ["id", "current_version"],
        ["upload_id", "version"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint("fk_photo_uploads_current_revision", "photo_uploads", type_="foreignkey")
    op.drop_table("media_write_intents")
    op.drop_table("photos")
    op.drop_table("photo_revisions")
    op.drop_table("photo_upload_revisions")
    op.drop_table("photo_uploads")
