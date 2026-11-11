"""Canonical safety outcomes reference retained business records, never private comments."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_safety_product_events"
down_revision: str | Sequence[str] | None = "0021_directional_blocks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
OLD_EVENT_SHAPE = (
    "((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_st"
    "ate IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved', 'goal.completed'"
    ") AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic_present IS NOT "
    "NULL AND shared_learning IS NOT NULL AND profile_version IS NULL AND visibility_"
    "version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.ready' AND prof"
    "ile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboarding_task IN ("
    "'find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NULL AND visi"
    "bility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shar"
    "ed_learning IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', 'discove"
    "ry.exposure_confirmed') AND visibility_version IS NOT NULL AND goal_id IS NULL A"
    "ND goal_version IS NULL AND profile_version IS NULL AND onboarding_task IS NULL "
    "AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL) OR"
    " (kind = 'auth.email_confirmed' AND goal_id IS NULL AND goal_version IS NULL AND"
    " profile_version IS NULL AND visibility_version IS NULL AND onboarding_task IS N"
    "ULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL"
    "))) OR (kind = 'ai_job.completed' AND ai_job_id IS NOT NULL AND ai_kind IS NOT N"
    "ULL AND ai_kind IN ('clarify_goal','suggest_subject','assess_photo','triage_repo"
    "rt') AND ai_state IS NOT NULL AND ai_state IN ('succeeded','failed','cancelled',"
    "'expired') AND (ai_reason IS NULL OR (ai_state IN ('failed','expired') AND ai_re"
    "ason IN ('transient','invalid_output','invalid_input','timeout','auth_unavailabl"
    "e','rate_limited','account_unavailable','stale_source','executor_lost'))) AND go"
    "al_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibilit"
    "y_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_le"
    "arning IS NULL AND onboarding_task IS NULL)"
)
NEW_EVENT_SHAPE = (
    "((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_"
    "state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved', 'goal.complete"
    "d') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic_present IS NO"
    "T NULL AND shared_learning IS NOT NULL AND profile_version IS NULL AND visibilit"
    "y_version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.ready' AND pr"
    "ofile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboarding_task IN"
    " ('find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NULL AND vi"
    "sibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND sh"
    "ared_learning IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', 'disco"
    "very.exposure_confirmed') AND visibility_version IS NOT NULL AND goal_id IS NULL"
    " AND goal_version IS NULL AND profile_version IS NULL AND onboarding_task IS NUL"
    "L AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL) "
    "OR (kind = 'auth.email_confirmed' AND goal_id IS NULL AND goal_version IS NULL A"
    "ND profile_version IS NULL AND visibility_version IS NULL AND onboarding_task IS"
    " NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NU"
    "LL))) OR (kind = 'ai_job.completed' AND ai_job_id IS NOT NULL AND ai_kind IS NOT"
    " NULL AND ai_kind IN ('clarify_goal','suggest_subject','assess_photo','triage_re"
    "port') AND ai_state IS NOT NULL AND ai_state IN ('succeeded','failed','cancelled"
    "','expired') AND (ai_reason IS NULL OR (ai_state IN ('failed','expired') AND ai_"
    "reason IN ('transient','invalid_output','invalid_input','timeout','auth_unavaila"
    "ble','rate_limited','account_unavailable','stale_source','executor_lost'))) AND "
    "goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibil"
    "ity_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_"
    "learning IS NULL AND onboarding_task IS NULL)) AND report_id IS NULL AND block_r"
    "elationship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR ((goal_"
    "id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility_v"
    "ersion IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learn"
    "ing IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NUL"
    "L AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind = 'report.created' AND "
    "report_id IS NOT NULL AND block_relationship_id IS NULL AND block_version IS NUL"
    "L AND blocked IS NULL) OR (kind = 'block.changed' AND report_id IS NULL AND bloc"
    "k_relationship_id IS NOT NULL AND block_version IS NOT NULL AND blocked IS NOT N"
    "ULL)))"
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_block_revisions_outcome",
        "block_revisions",
        ["relationship_id", "blocker_id", "version", "blocked"],
    )
    op.add_column("product_events", sa.Column("report_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("block_relationship_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("block_version", sa.Integer(), nullable=True))
    op.add_column("product_events", sa.Column("blocked", sa.Boolean(), nullable=True))
    op.create_foreign_key(
        "fk_product_events_report_owner",
        "product_events",
        "profile_reports",
        ["report_id", "account_id"],
        ["id", "reporter_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_product_events_block_outcome",
        "product_events",
        "block_revisions",
        ["block_relationship_id", "account_id", "block_version", "blocked"],
        ["relationship_id", "blocker_id", "version", "blocked"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", NEW_EVENT_SHAPE
    )


def downgrade() -> None:
    retained = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM product_events "
            "WHERE kind IN ('report.created','block.changed'))"
        )
    )
    if retained:
        raise RuntimeError("Cannot downgrade retained canonical safety history")
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", OLD_EVENT_SHAPE
    )
    op.drop_constraint("fk_product_events_block_outcome", "product_events", type_="foreignkey")
    op.drop_constraint("fk_product_events_report_owner", "product_events", type_="foreignkey")
    for column in ("blocked", "block_version", "block_relationship_id", "report_id"):
        op.drop_column("product_events", column)
    op.drop_constraint("uq_block_revisions_outcome", "block_revisions", type_="unique")
