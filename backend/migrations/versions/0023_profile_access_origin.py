"""Retain original execution links on genuine peer-profile disclosure references."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_profile_access_origin"
down_revision: str | Sequence[str] | None = "0022_safety_product_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("profile_access_contexts", sa.Column("request_id", sa.Uuid(), nullable=True))
    op.add_column("profile_access_contexts", sa.Column("action_id", sa.Uuid(), nullable=True))
    op.add_column("profile_access_contexts", sa.Column("trace_id", sa.String(32), nullable=True))
    op.add_column("profile_access_contexts", sa.Column("span_id", sa.String(16), nullable=True))
    op.create_check_constraint(
        op.f("ck_profile_access_contexts_origin_request"),
        "profile_access_contexts",
        "request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND span_id IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_profile_access_contexts_origin_trace_pair"),
        "profile_access_contexts",
        "(trace_id IS NULL AND span_id IS NULL) OR "
        "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
        "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0', 32) AND "
        "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))",
    )


def downgrade() -> None:
    retained = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM profile_access_contexts WHERE request_id IS NOT NULL)"
        )
    )
    if retained:
        raise RuntimeError("Cannot downgrade retained profile disclosure execution history")
    op.drop_constraint(
        op.f("ck_profile_access_contexts_origin_trace_pair"),
        "profile_access_contexts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_profile_access_contexts_origin_request"), "profile_access_contexts", type_="check"
    )
    for column in ("span_id", "trace_id", "action_id", "request_id"):
        op.drop_column("profile_access_contexts", column)
