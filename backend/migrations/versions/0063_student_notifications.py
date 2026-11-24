"""Proposed descriptive revision; parent must reconcile actual migration head at integration."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0063_student_notifications"
down_revision: str | Sequence[str] | None = "0062_google_display"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "student_notification_consumers",
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name"),
        sa.CheckConstraint("name = 'student_push_v1'", name="known_consumer"),
    )
    op.create_table(
        "student_notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["event_id"], ["product_events.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipient_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["relationship_id"], ["relationships.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "event_id", "recipient_id", name="uq_student_notification_event_recipient"
        ),
        sa.CheckConstraint(
            "kind IN ('message','request','accepted_connection')", name="known_kind"
        ),
        sa.CheckConstraint(
            "state IN ('pending','claimed','sending','delivered','cancelled','rejected','unknown')",
            name="known_state",
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 3", name="bounded_attempts"),
        sa.CheckConstraint("actor_id <> recipient_id", name="different_actor_recipient"),
        sa.CheckConstraint(
            "expires_at > created_at AND due_at >= created_at", name="valid_delivery_times"
        ),
        sa.CheckConstraint(
            "((state IN ('claimed','sending')) AND lease_token IS NOT NULL "
            "AND lease_until IS NOT NULL) OR ((state NOT IN ('claimed','sending')) "
            "AND lease_token IS NULL AND lease_until IS NULL)",
            name="lease_shape",
        ),
    )
    op.create_index(
        "ix_student_notifications_due", "student_notification_deliveries", ["state", "due_at", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_student_notifications_due", table_name="student_notification_deliveries")
    op.drop_table("student_notification_deliveries")
    op.drop_table("student_notification_consumers")
