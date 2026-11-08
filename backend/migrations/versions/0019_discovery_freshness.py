"""Separate exposure pause/source facts and genuine user confirmations; no lifecycle mode."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_discovery_freshness"
down_revision: str | Sequence[str] | None = "0018_ai_product_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_EVENT_SHAPE = (
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
NEW_EVENT_SHAPE = (
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
    "'profile.restored', 'discovery.exposure_confirmed') AND "
    "visibility_version IS NOT NULL AND goal_id IS NULL AND goal_version "
    "IS NULL AND profile_version IS NULL AND onboarding_task IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS "
    "NULL) OR (kind = 'auth.email_confirmed' AND goal_id IS NULL AND "
    "goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND onboarding_task IS NULL AND subject_id "
    "IS NULL AND topic_present IS NULL AND shared_learning IS NULL))) OR "
    "(kind = 'ai_job.completed' AND ai_job_id IS NOT NULL AND ai_kind IS "
    "NOT NULL AND ai_kind IN ('clarify_goal','suggest_subject',"
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
    op.create_table(
        "discovery_freshness_policies",
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("inactivity_seconds", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("version"),
        sa.CheckConstraint("version > 0 AND inactivity_seconds > 0", name="positive_policy"),
    )
    policies = sa.table(
        "discovery_freshness_policies",
        sa.column("version", sa.Integer()),
        sa.column("inactivity_seconds", sa.Integer()),
        sa.column("published_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        sa.insert(policies).values(
            version=1,
            inactivity_seconds=2592000,
            published_at=sa.func.clock_timestamp(),
        )
    )
    op.add_column(
        "visibility_write_intents",
        sa.Column("confirmed_exposure_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "visibility_write_intents",
        sa.Column("previous_exposure_paused_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_visibility_write_intents_exposure_confirmation"),
        "visibility_write_intents",
        "(confirmed_exposure_at IS NULL AND previous_exposure_paused_at IS NULL) OR "
        "(confirmed_exposure_at IS NOT NULL AND previous_exposure_paused_at IS NOT NULL AND "
        "confirmed_exposure_at >= previous_exposure_paused_at)",
    )
    op.create_unique_constraint(
        "uq_visibility_intents_exposure_confirmation",
        "visibility_write_intents",
        ["account_id", "key", "confirmed_exposure_at"],
    )
    op.create_table(
        "discovery_exposure",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("inactivity_seconds", sa.Integer(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_key", sa.String(128), nullable=True),
        sa.PrimaryKeyConstraint("account_id"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["profile_activations.account_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "confirmation_key", "confirmed_at"],
            [
                "visibility_write_intents.account_id",
                "visibility_write_intents.key",
                "visibility_write_intents.confirmed_exposure_at",
            ],
            name="fk_discovery_exposure_actual_confirmation",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint("inactivity_seconds > 0", name="positive_inactivity"),
        sa.CheckConstraint("last_activity_at >= confirmed_at", name="ordered_activity"),
        sa.CheckConstraint("paused_at IS NULL OR paused_at >= confirmed_at", name="ordered_pause"),
        sa.Index("ix_discovery_exposure_activity", "last_activity_at", "account_id"),
    )
    # These are actual pre-existing business timestamps, not fabricated events or
    # a claim that old users clicked the new explicit exposure-return action.
    op.execute(
        sa.text("""
        WITH foreground AS (
            SELECT account_id, completed_at AS at FROM profile_activations
            UNION ALL SELECT account_id, saved_at FROM profile_revisions
            UNION ALL SELECT account_id, saved_at FROM help_revisions
            UNION ALL SELECT account_id, issued_at FROM sessions
            UNION ALL SELECT account_id, created_at FROM photo_uploads
            UNION ALL SELECT account_id, changed_at FROM visibility_revisions
            UNION ALL SELECT account_id, occurred_at FROM product_events
              WHERE kind IN ('auth.email_confirmed', 'profile.ready', 'goal.saved',
                             'goal.completed', 'profile.hidden', 'profile.restored')
        ), activity AS (
            SELECT account_id, max(at) AS last_activity_at FROM foreground GROUP BY account_id
        ), confirmation AS (
            SELECT account_id, max(changed_at) AS confirmed_at FROM visibility_revisions
              WHERE hidden_at IS NULL GROUP BY account_id
        )
        INSERT INTO discovery_exposure
            (account_id, inactivity_seconds, last_activity_at, confirmed_at,
             paused_at, confirmation_key)
        SELECT a.account_id, 2592000, f.last_activity_at, c.confirmed_at,
               CASE WHEN f.last_activity_at + INTERVAL '30 days' <= clock_timestamp()
                    THEN f.last_activity_at + INTERVAL '30 days' ELSE NULL END,
               NULL
        FROM profile_activations a
        JOIN activity f ON f.account_id = a.account_id
        JOIN confirmation c ON c.account_id = a.account_id
    """)
    )

    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", NEW_EVENT_SHAPE
    )


def downgrade() -> None:
    # Retained explicit exposure-confirmation events prevent an incompatible rollback.
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", OLD_EVENT_SHAPE
    )
    op.drop_table("discovery_exposure")
    op.drop_constraint(
        "uq_visibility_intents_exposure_confirmation", "visibility_write_intents", type_="unique"
    )
    op.drop_constraint(
        op.f("ck_visibility_write_intents_exposure_confirmation"),
        "visibility_write_intents",
        type_="check",
    )
    op.drop_column("visibility_write_intents", "previous_exposure_paused_at")
    op.drop_column("visibility_write_intents", "confirmed_exposure_at")
    op.drop_table("discovery_freshness_policies")
