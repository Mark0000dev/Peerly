"""One canonical AI terminal outcome per retained job; no second event journal."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_ai_product_events"
down_revision: str | Sequence[str] | None = "0017_ai_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_SHAPE = (
    "(kind IN ('goal.saved', 'goal.completed') AND goal_id IS NOT NULL AND "
    "goal_version IS NOT NULL AND topic_present IS NOT NULL AND "
    "shared_learning IS NOT NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND onboarding_task IS NULL) OR (kind = "
    "'profile.ready' AND profile_version IS NOT NULL AND onboarding_task "
    "IS NOT NULL AND onboarding_task IN ('find_help', 'offer_help') AND "
    "goal_id IS NULL AND goal_version IS NULL AND visibility_version IS "
    "NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL) OR (kind IN ('profile.hidden', "
    "'profile.restored') AND visibility_version IS NOT NULL AND goal_id IS "
    "NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "onboarding_task IS NULL AND subject_id IS NULL AND topic_present IS "
    "NULL AND shared_learning IS NULL) OR (kind = 'auth.email_confirmed' "
    "AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS "
    "NULL AND visibility_version IS NULL AND onboarding_task IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS "
    "NULL)"
)
NEW_SHAPE = (
    "((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS "
    "NULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN "
    "('goal.saved', 'goal.completed') AND goal_id IS NOT NULL AND "
    "goal_version IS NOT NULL AND topic_present IS NOT NULL AND "
    "shared_learning IS NOT NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND onboarding_task IS NULL) OR (kind = "
    "'profile.ready' AND profile_version IS NOT NULL AND onboarding_task "
    "IS NOT NULL AND onboarding_task IN ('find_help', 'offer_help') AND "
    "goal_id IS NULL AND goal_version IS NULL AND visibility_version IS "
    "NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL) OR (kind IN ('profile.hidden', "
    "'profile.restored') AND visibility_version IS NOT NULL AND goal_id IS "
    "NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "onboarding_task IS NULL AND subject_id IS NULL AND topic_present IS "
    "NULL AND shared_learning IS NULL) OR (kind = 'auth.email_confirmed' "
    "AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS "
    "NULL AND visibility_version IS NULL AND onboarding_task IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS "
    "NULL))) OR (kind = 'ai_job.completed' AND ai_job_id IS NOT NULL AND "
    "ai_kind IS NOT NULL AND ai_kind IN ('clarify_goal','suggest_subject',"
    "'assess_photo','triage_report') AND ai_state IS NOT NULL AND ai_state "
    "IN ('succeeded','failed','cancelled','expired') AND (ai_reason IS "
    "NULL OR (ai_state IN ('failed','expired') AND ai_reason IN "
    "('transient','invalid_output','invalid_input','timeout',"
    "'auth_unavailable','rate_limited','account_unavailable',"
    "'stale_source','executor_lost'))) AND goal_id IS NULL AND "
    "goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present "
    "IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL)"
)


def upgrade() -> None:
    op.add_column("product_events", sa.Column("ai_job_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("ai_kind", sa.String(24), nullable=True))
    op.add_column("product_events", sa.Column("ai_state", sa.String(16), nullable=True))
    op.add_column("product_events", sa.Column("ai_reason", sa.String(32), nullable=True))
    op.create_foreign_key(
        "fk_product_events_ai_job_owner_kind",
        "product_events",
        "ai_jobs",
        ["ai_job_id", "account_id", "ai_kind"],
        ["id", "actor_id", "kind"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", NEW_SHAPE
    )


def downgrade() -> None:
    # Existing AI outcomes intentionally prevent an incompatible downgrade.
    # Never delete retained canonical history to make a rollback appear successful.
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", OLD_SHAPE
    )
    op.drop_constraint("fk_product_events_ai_job_owner_kind", "product_events", type_="foreignkey")
    op.drop_column("product_events", "ai_reason")
    op.drop_column("product_events", "ai_state")
    op.drop_column("product_events", "ai_kind")
    op.drop_column("product_events", "ai_job_id")
