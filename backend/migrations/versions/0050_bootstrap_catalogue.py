"""Retain explicitly authored catalogue import provenance; no sample data or users."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_bootstrap_catalogue"
down_revision: str | Sequence[str] | None = "0049_message_image_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bootstrap_catalogue_manifests",
        sa.Column("version", sa.String(64), primary_key=True),
        sa.Column("sha256", sa.LargeBinary(), nullable=False),
        sa.Column("canonical_json", sa.Text(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject_count", sa.Integer(), nullable=False),
        sa.Column("alias_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("version ~ '^[A-Za-z0-9._-]{1,64}$'", name="valid_version"),
        sa.CheckConstraint("octet_length(sha256)=32", name="source_digest_length"),
        sa.CheckConstraint(
            "octet_length(canonical_json) BETWEEN 1 AND 2097152", name="bounded_source"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(canonical_json::jsonb)='object' AND canonical_json::jsonb<>'{}'::jsonb",
            name="actual_source_object",
        ),
        sa.CheckConstraint(
            "sha256(convert_to(canonical_json,'UTF8'))=sha256", name="source_digest_matches"
        ),
        sa.CheckConstraint("subject_count BETWEEN 1 AND 5000", name="bounded_subject_count"),
        sa.CheckConstraint(
            "alias_count BETWEEN 0 AND subject_count*20", name="bounded_alias_count"
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM bootstrap_catalogue_manifests)")):
        raise RuntimeError("Refusing to drop retained authored catalogue import provenance")
    op.drop_table("bootstrap_catalogue_manifests")
