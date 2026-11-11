"""Canonical private-pass outcomes reference the retained immutable revision."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_discovery_pass_events"
down_revision: str | Sequence[str] | None = "0025_discovery_private_passes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREVIOUS_REFERENCE_SHAPE: str = (
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

REFERENCE_SHAPE: str = (
    "((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL AND a"
    "i_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved', 'goal.comple"
    "ted') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic_present IS "
    "NOT NULL AND shared_learning IS NOT NULL AND profile_version IS NULL AND visibil"
    "ity_version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.ready' AND "
    "profile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboarding_task "
    "IN ('find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', 'dis"
    "covery.exposure_confirmed') AND visibility_version IS NOT NULL AND goal_id IS NU"
    "LL AND goal_version IS NULL AND profile_version IS NULL AND onboarding_task IS N"
    "ULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL"
    ") OR (kind = 'auth.email_confirmed' AND goal_id IS NULL AND goal_version IS NULL"
    " AND profile_version IS NULL AND visibility_version IS NULL AND onboarding_task "
    "IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS "
    "NULL))) OR (kind = 'ai_job.completed' AND ai_job_id IS NOT NULL AND ai_kind IS N"
    "OT NULL AND ai_kind IN ('clarify_goal','suggest_subject','assess_photo','triage_"
    "report') AND ai_state IS NOT NULL AND ai_state IN ('succeeded','failed','cancell"
    "ed','expired') AND (ai_reason IS NULL OR (ai_state IN ('failed','expired') AND a"
    "i_reason IN ('transient','invalid_output','invalid_input','timeout','auth_unavai"
    "lable','rate_limited','account_unavailable','stale_source','executor_lost'))) AN"
    "D goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visib"
    "ility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND share"
    "d_learning IS NULL AND onboarding_task IS NULL)) AND report_id IS NULL AND block"
    "_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR ((goa"
    "l_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibility"
    "_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_lea"
    "rning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS N"
    "ULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind = 'report.created' AN"
    "D report_id IS NOT NULL AND block_relationship_id IS NULL AND block_version IS N"
    "ULL AND blocked IS NULL) OR (kind = 'block.changed' AND report_id IS NULL AND bl"
    "ock_relationship_id IS NOT NULL AND block_version IS NOT NULL AND blocked IS NOT"
    " NULL)))) AND private_pass_id IS NULL AND private_pass_version IS NULL AND priva"
    "te_passed IS NULL) OR (kind = 'discovery.pass_changed' AND private_pass_id IS NO"
    "T NULL AND private_pass_version IS NOT NULL AND private_passed IS NOT NULL AND g"
    "oal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibili"
    "ty_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_l"
    "earning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block"
    "_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL)"
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_private_pass_revision_outcome",
        "private_pass_revisions",
        ["pass_id", "version", "account_id", "passed"],
    )
    op.add_column("product_events", sa.Column("private_pass_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("private_pass_version", sa.Integer(), nullable=True))
    op.add_column("product_events", sa.Column("private_passed", sa.Boolean(), nullable=True))
    op.create_foreign_key(
        "fk_product_events_private_pass_outcome",
        "product_events",
        "private_pass_revisions",
        ["private_pass_id", "private_pass_version", "account_id", "private_passed"],
        ["pass_id", "version", "account_id", "passed"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", REFERENCE_SHAPE
    )


def downgrade() -> None:
    retained = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM product_events WHERE private_pass_id IS NOT NULL)"
            )
        )
        .scalar_one()
    )
    if retained:
        raise RuntimeError("Cannot remove retained private discovery outcomes")
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", PREVIOUS_REFERENCE_SHAPE
    )
    op.drop_constraint(
        "fk_product_events_private_pass_outcome", "product_events", type_="foreignkey"
    )
    op.drop_column("product_events", "private_passed")
    op.drop_column("product_events", "private_pass_version")
    op.drop_column("product_events", "private_pass_id")
    op.drop_constraint("uq_private_pass_revision_outcome", "private_pass_revisions", type_="unique")
