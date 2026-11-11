"""Retain initiating execution links independently of temporary email secrets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_email_origin"
down_revision: str | Sequence[str] | None = "0005_callback_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("email_outbox", sa.Column("origin_request_id", sa.Uuid(), nullable=True))
    op.add_column("email_outbox", sa.Column("origin_action_id", sa.Uuid(), nullable=True))
    op.add_column("email_outbox", sa.Column("origin_trace_id", sa.String(32), nullable=True))
    op.add_column("email_outbox", sa.Column("origin_span_id", sa.String(16), nullable=True))
    op.create_check_constraint(
        op.f("ck_email_outbox_origin_request_context"),
        "email_outbox",
        "origin_request_id IS NOT NULL OR (origin_action_id IS NULL AND "
        "origin_trace_id IS NULL AND origin_span_id IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_email_outbox_origin_trace_pair"),
        "email_outbox",
        "(origin_trace_id IS NULL AND origin_span_id IS NULL) OR "
        "(origin_trace_id IS NOT NULL AND origin_span_id IS NOT NULL AND "
        "origin_trace_id ~ '^[0-9a-f]{32}$' AND origin_trace_id != repeat('0', 32) AND "
        "origin_span_id ~ '^[0-9a-f]{16}$' AND origin_span_id != repeat('0', 16))",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_email_outbox_origin_trace_pair"), "email_outbox", type_="check")
    op.drop_constraint(
        op.f("ck_email_outbox_origin_request_context"), "email_outbox", type_="check"
    )
    op.drop_column("email_outbox", "origin_span_id")
    op.drop_column("email_outbox", "origin_trace_id")
    op.drop_column("email_outbox", "origin_action_id")
    op.drop_column("email_outbox", "origin_request_id")
