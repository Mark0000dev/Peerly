"""Canonical committed outcomes and actual correlations, with no private payload column."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_product_events"
down_revision: str | Sequence[str] | None = "0015_media_origins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("occurrence_key", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=True),
        sa.Column("goal_version", sa.Integer(), nullable=True),
        sa.Column("profile_version", sa.Integer(), nullable=True),
        sa.Column("visibility_version", sa.Integer(), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("topic_present", sa.Boolean(), nullable=True),
        sa.Column("shared_learning", sa.Boolean(), nullable=True),
        sa.Column("onboarding_task", sa.String(16), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(32), nullable=True),
        sa.Column("span_id", sa.String(16), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["account_id", "goal_id", "goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "profile_version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "visibility_version"],
            ["visibility_revisions.account_id", "visibility_revisions.version"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "account_id", "kind", "occurrence_key", name="uq_product_events_occurrence"
        ),
        sa.CheckConstraint("schema_version = 1", name="known_schema_version"),
        sa.CheckConstraint(
            "occurrence_key ~ '^[A-Za-z0-9:_-]{1,100}$'", name="occurrence_key_shape"
        ),
        sa.CheckConstraint(
            "(kind IN ('goal.saved', 'goal.completed') AND goal_id IS NOT NULL AND "
            "goal_version IS NOT NULL AND topic_present IS NOT NULL AND "
            "shared_learning IS NOT NULL AND profile_version IS NULL AND "
            "visibility_version IS NULL AND onboarding_task IS NULL) OR "
            "(kind = 'profile.ready' AND profile_version IS NOT NULL AND "
            "onboarding_task IS NOT NULL AND onboarding_task IN ('find_help', 'offer_help') AND "
            "goal_id IS NULL AND goal_version IS NULL AND visibility_version IS NULL AND "
            "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL) OR "
            "(kind IN ('profile.hidden', 'profile.restored') AND "
            "visibility_version IS NOT NULL AND "
            "goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
            "onboarding_task IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
            "shared_learning IS NULL) OR "
            "(kind = 'auth.email_confirmed' AND goal_id IS NULL AND goal_version IS NULL AND "
            "profile_version IS NULL AND visibility_version IS NULL AND "
            "onboarding_task IS NULL AND "
            "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL)",
            name="event_reference_shape",
        ),
        sa.CheckConstraint(
            "request_id IS NOT NULL OR "
            "(action_id IS NULL AND trace_id IS NULL AND span_id IS NULL)",
            name="origin_request_context",
        ),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR "
            "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
            "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0', 32) AND "
            "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))",
            name="origin_trace_pair",
        ),
    )
    op.create_index(
        "ix_product_events_actor_time", "product_events", ["account_id", "occurred_at", "id"]
    )
    op.create_index("ix_product_events_kind_time", "product_events", ["kind", "occurred_at", "id"])


def downgrade() -> None:
    op.drop_table("product_events")
