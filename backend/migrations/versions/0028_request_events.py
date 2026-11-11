"""Canonical request changes retain actual source and human/system initiation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_request_events"
down_revision: str | Sequence[str] | None = "0027_requests_and_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREVIOUS_REFERENCE_SHAPE: str = (
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

REFERENCE_SHAPE: str = (
    "((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL AND"
    " ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved', 'goal.comp"
    "leted') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic_present I"
    "S NOT NULL AND shared_learning IS NOT NULL AND profile_version IS NULL AND visib"
    "ility_version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.ready' AN"
    "D profile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboarding_tas"
    "k IN ('find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NULL AN"
    "D visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AN"
    "D shared_learning IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', 'd"
    "iscovery.exposure_confirmed') AND visibility_version IS NOT NULL AND goal_id IS "
    "NULL AND goal_version IS NULL AND profile_version IS NULL AND onboarding_task IS"
    " NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NU"
    "LL) OR (kind = 'auth.email_confirmed' AND goal_id IS NULL AND goal_version IS NU"
    "LL AND profile_version IS NULL AND visibility_version IS NULL AND onboarding_tas"
    "k IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_learning I"
    "S NULL))) OR (kind = 'ai_job.completed' AND ai_job_id IS NOT NULL AND ai_kind IS"
    " NOT NULL AND ai_kind IN ('clarify_goal','suggest_subject','assess_photo','triag"
    "e_report') AND ai_state IS NOT NULL AND ai_state IN ('succeeded','failed','cance"
    "lled','expired') AND (ai_reason IS NULL OR (ai_state IN ('failed','expired') AND"
    " ai_reason IN ('transient','invalid_output','invalid_input','timeout','auth_unav"
    "ailable','rate_limited','account_unavailable','stale_source','executor_lost'))) "
    "AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND vis"
    "ibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND sha"
    "red_learning IS NULL AND onboarding_task IS NULL)) AND report_id IS NULL AND blo"
    "ck_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR ((g"
    "oal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibili"
    "ty_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared_l"
    "earning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind = 'report.created' "
    "AND report_id IS NOT NULL AND block_relationship_id IS NULL AND block_version IS"
    " NULL AND blocked IS NULL) OR (kind = 'block.changed' AND report_id IS NULL AND "
    "block_relationship_id IS NOT NULL AND block_version IS NOT NULL AND blocked IS N"
    "OT NULL)))) AND private_pass_id IS NULL AND private_pass_version IS NULL AND pri"
    "vate_passed IS NULL) OR (kind = 'discovery.pass_changed' AND private_pass_id IS "
    "NOT NULL AND private_pass_version IS NOT NULL AND private_passed IS NOT NULL AND"
    " goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND visibi"
    "lity_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND shared"
    "_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind "
    "IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND blo"
    "ck_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL)) AND c"
    "onnection_request_id IS NULL AND connection_request_version IS NULL AND connecti"
    "on_request_state IS NULL AND connection_request_recipient_id IS NULL AND request"
    "_initiator_id IS NULL) OR (kind = 'request.changed' AND connection_request_id IS"
    " NOT NULL AND connection_request_version IS NOT NULL AND connection_request_stat"
    "e IS NOT NULL AND connection_request_recipient_id IS NOT NULL AND (request_initi"
    "ator_id IS NULL OR request_initiator_id IN (account_id, connection_request_recip"
    "ient_id)) AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NU"
    "LL AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NU"
    "LL AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL"
    " AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS"
    " NULL AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS"
    " NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_p"
    "assed IS NULL)"
)


def upgrade() -> None:
    op.add_column("product_events", sa.Column("connection_request_id", sa.Uuid(), nullable=True))
    op.add_column(
        "product_events", sa.Column("connection_request_version", sa.Integer(), nullable=True)
    )
    op.add_column(
        "product_events", sa.Column("connection_request_state", sa.String(24), nullable=True)
    )
    op.add_column(
        "product_events", sa.Column("connection_request_recipient_id", sa.Uuid(), nullable=True)
    )
    op.add_column("product_events", sa.Column("request_initiator_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_product_events_request_source",
        "product_events",
        "connection_requests",
        ["connection_request_id", "account_id", "connection_request_recipient_id"],
        ["id", "sender_id", "recipient_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_product_events_request_revision",
        "product_events",
        "request_revisions",
        ["connection_request_id", "connection_request_version", "connection_request_state"],
        ["request_id", "version", "state"],
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
                "SELECT EXISTS (SELECT 1 FROM product_events "
                "WHERE connection_request_id IS NOT NULL)"
            )
        )
        .scalar_one()
    )
    if retained:
        raise RuntimeError("Cannot remove retained canonical request outcomes")
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", PREVIOUS_REFERENCE_SHAPE
    )
    op.drop_constraint("fk_product_events_request_revision", "product_events", type_="foreignkey")
    op.drop_constraint("fk_product_events_request_source", "product_events", type_="foreignkey")
    op.drop_column("product_events", "request_initiator_id")
    op.drop_column("product_events", "connection_request_recipient_id")
    op.drop_column("product_events", "connection_request_state")
    op.drop_column("product_events", "connection_request_version")
    op.drop_column("product_events", "connection_request_id")
