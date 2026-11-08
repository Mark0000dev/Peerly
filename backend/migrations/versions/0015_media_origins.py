"""Retain actual upload/finalization origins; never fabricate old execution links."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_media_origins"
down_revision: str | Sequence[str] | None = "0014_profile_activation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_execution_origins",
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(32), nullable=True),
        sa.Column("span_id", sa.String(16), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("upload_id", "phase"),
        sa.ForeignKeyConstraint(["upload_id"], ["photo_uploads.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("phase IN ('created', 'queued')", name="known_phase"),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR "
            "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
            "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0', 32) AND "
            "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))",
            name="origin_trace_pair",
        ),
    )


def downgrade() -> None:
    op.drop_table("media_execution_origins")
