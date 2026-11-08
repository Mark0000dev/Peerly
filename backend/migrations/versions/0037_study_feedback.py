"""Retained explicit study reports, evidence-bound feedback and prompt receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_study_feedback"
down_revision: str | Sequence[str] | None = "0036_change_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
PREVIOUS_EVENT_SHAPE = (
    "((((((((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL "
    "AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved', "
    "'goal.completed') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic_present"
    " IS NOT NULL AND shared_learning IS NOT NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.ready' AND "
    "profile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboarding_task IN "
    "('find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', "
    "'discovery.exposure_confirmed') AND visibility_version IS NOT NULL AND goal_id IS NULL "
    "AND goal_version IS NULL AND profile_version IS NULL AND onboarding_task IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL) OR (kind = "
    "'auth.email_confirmed' AND goal_id IS NULL AND goal_version IS NULL AND profile_version "
    "IS NULL AND visibility_version IS NULL AND onboarding_task IS NULL AND subject_id IS "
    "NULL AND topic_present IS NULL AND shared_learning IS NULL))) OR (kind = "
    "'ai_job.completed' AND ai_job_id IS NOT NULL AND ai_kind IS NOT NULL AND ai_kind IN "
    "('clarify_goal','suggest_subject','assess_photo','triage_report') AND ai_state IS NOT "
    "NULL AND ai_state IN ('succeeded','failed','cancelled','expired') AND (ai_reason IS NULL"
    " OR (ai_state IN ('failed','expired') AND ai_reason IN "
    "('transient','invalid_output','invalid_input','timeout','auth_unavailable','rate_limited','account_unavailable','stale_source','executor_lost')))"
    " AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL)) AND report_id IS NULL AND "
    "block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR "
    "((goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind = 'report.created' AND "
    "report_id IS NOT NULL AND block_relationship_id IS NULL AND block_version IS NULL AND "
    "blocked IS NULL) OR (kind = 'block.changed' AND report_id IS NULL AND "
    "block_relationship_id IS NOT NULL AND block_version IS NOT NULL AND blocked IS NOT "
    "NULL)))) AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed"
    " IS NULL) OR (kind = 'discovery.pass_changed' AND private_pass_id IS NOT NULL AND "
    "private_pass_version IS NOT NULL AND private_passed IS NOT NULL AND goal_id IS NULL AND "
    "goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND "
    "onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL "
    "AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND "
    "block_version IS NULL AND blocked IS NULL)) AND connection_request_id IS NULL AND "
    "connection_request_version IS NULL AND connection_request_state IS NULL AND "
    "connection_request_recipient_id IS NULL AND request_initiator_id IS NULL) OR (kind = "
    "'request.changed' AND connection_request_id IS NOT NULL AND connection_request_version "
    "IS NOT NULL AND connection_request_state IS NOT NULL AND connection_request_recipient_id"
    " IS NOT NULL AND (request_initiator_id IS NULL OR request_initiator_id IN (account_id, "
    "connection_request_recipient_id)) AND goal_id IS NULL AND goal_version IS NULL AND "
    "profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND "
    "topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND "
    "ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND "
    "report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND "
    "blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND "
    "private_passed IS NULL)) AND request_view_ack_id IS NULL) OR (kind = "
    "'request.view_acknowledged' AND request_view_ack_id IS NOT NULL AND goal_id IS NULL AND "
    "goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND "
    "onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL "
    "AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND "
    "block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND "
    "private_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS "
    "NULL AND connection_request_version IS NULL AND connection_request_state IS NULL AND "
    "connection_request_recipient_id IS NULL AND request_initiator_id IS NULL)) AND "
    "message_operation_id IS NULL AND message_operation_state IS NULL) OR "
    "(message_operation_id IS NOT NULL AND message_operation_state IS NOT NULL AND "
    "((kind='message.confirmed' AND message_operation_state='confirmed') OR "
    "(kind='message.cancelled' AND message_operation_state='cancelled')) AND goal_id IS NULL "
    "AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND "
    "onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL "
    "AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND "
    "block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND "
    "private_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS "
    "NULL AND connection_request_version IS NULL AND connection_request_state IS NULL AND "
    "connection_request_recipient_id IS NULL AND request_view_ack_id IS NULL AND "
    "request_initiator_id IS NULL)) AND conversation_read_id IS NULL AND read_conversation_id"
    " IS NULL) OR (kind='conversation.read_acknowledged' AND conversation_read_id IS NOT NULL"
    " AND read_conversation_id IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND "
    "profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND "
    "topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND "
    "ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND "
    "report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND "
    "blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND "
    "private_passed IS NULL AND connection_request_id IS NULL AND connection_request_version "
    "IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS NULL"
    " AND message_operation_id IS NULL AND message_operation_state IS NULL AND "
    "request_view_ack_id IS NULL AND request_initiator_id IS NULL)) AND goal_share_id IS NULL"
    " AND goal_share_context_version IS NULL AND goal_share_conversation_id IS NULL) OR "
    "(kind='conversation.goal_shared' AND goal_share_id IS NOT NULL AND "
    "goal_share_context_version IS NOT NULL AND goal_share_conversation_id IS NOT NULL AND "
    "goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND "
    "block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND "
    "private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND "
    "connection_request_id IS NULL AND connection_request_version IS NULL AND "
    "connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND "
    "conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id "
    "IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND "
    "request_initiator_id IS NULL)) AND operator_audit_id IS NULL AND operator_access_version"
    " IS NULL AND operator_action IS NULL) OR (kind='operator.inspected' AND "
    "operator_audit_id IS NOT NULL AND operator_access_version IS NOT NULL AND "
    "operator_action IS NOT NULL AND operator_action IN "
    "('search_accounts','read_account','read_conversation_messages') AND goal_id IS NULL AND "
    "goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND "
    "onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL "
    "AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND "
    "block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND "
    "private_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS "
    "NULL AND connection_request_version IS NULL AND connection_request_state IS NULL AND "
    "connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND "
    "goal_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND "
    "conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id "
    "IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND "
    "request_initiator_id IS NULL)"
)
EVENT_SHAPE = (
    "((((((((((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL"
    " AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved', "
    "'goal.completed') AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic_present"
    " IS NOT NULL AND shared_learning IS NOT NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND onboarding_task IS NULL) OR (kind = 'profile.ready' AND "
    "profile_version IS NOT NULL AND onboarding_task IS NOT NULL AND onboarding_task IN "
    "('find_help', 'offer_help') AND goal_id IS NULL AND goal_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL) OR (kind IN ('profile.hidden', 'profile.restored', "
    "'discovery.exposure_confirmed') AND visibility_version IS NOT NULL AND goal_id IS NULL "
    "AND goal_version IS NULL AND profile_version IS NULL AND onboarding_task IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL) OR (kind = "
    "'auth.email_confirmed' AND goal_id IS NULL AND goal_version IS NULL AND profile_version "
    "IS NULL AND visibility_version IS NULL AND onboarding_task IS NULL AND subject_id IS "
    "NULL AND topic_present IS NULL AND shared_learning IS NULL))) OR (kind = "
    "'ai_job.completed' AND ai_job_id IS NOT NULL AND ai_kind IS NOT NULL AND ai_kind IN "
    "('clarify_goal','suggest_subject','assess_photo','triage_report') AND ai_state IS NOT "
    "NULL AND ai_state IN ('succeeded','failed','cancelled','expired') AND (ai_reason IS NULL"
    " OR (ai_state IN ('failed','expired') AND ai_reason IN "
    "('transient','invalid_output','invalid_input','timeout','auth_unavailable','rate_limited','account_unavailable','stale_source','executor_lost')))"
    " AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL)) AND report_id IS NULL AND "
    "block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL) OR "
    "((goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL) AND ((kind = 'report.created' AND "
    "report_id IS NOT NULL AND block_relationship_id IS NULL AND block_version IS NULL AND "
    "blocked IS NULL) OR (kind = 'block.changed' AND report_id IS NULL AND "
    "block_relationship_id IS NOT NULL AND block_version IS NOT NULL AND blocked IS NOT "
    "NULL)))) AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed"
    " IS NULL) OR (kind = 'discovery.pass_changed' AND private_pass_id IS NOT NULL AND "
    "private_pass_version IS NOT NULL AND private_passed IS NOT NULL AND goal_id IS NULL AND "
    "goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND "
    "onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL "
    "AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND "
    "block_version IS NULL AND blocked IS NULL)) AND connection_request_id IS NULL AND "
    "connection_request_version IS NULL AND connection_request_state IS NULL AND "
    "connection_request_recipient_id IS NULL AND request_initiator_id IS NULL) OR (kind = "
    "'request.changed' AND connection_request_id IS NOT NULL AND connection_request_version "
    "IS NOT NULL AND connection_request_state IS NOT NULL AND connection_request_recipient_id"
    " IS NOT NULL AND (request_initiator_id IS NULL OR request_initiator_id IN (account_id, "
    "connection_request_recipient_id)) AND goal_id IS NULL AND goal_version IS NULL AND "
    "profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND "
    "topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND "
    "ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND "
    "report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND "
    "blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND "
    "private_passed IS NULL)) AND request_view_ack_id IS NULL) OR (kind = "
    "'request.view_acknowledged' AND request_view_ack_id IS NOT NULL AND goal_id IS NULL AND "
    "goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND "
    "onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL "
    "AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND "
    "block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND "
    "private_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS "
    "NULL AND connection_request_version IS NULL AND connection_request_state IS NULL AND "
    "connection_request_recipient_id IS NULL AND request_initiator_id IS NULL)) AND "
    "message_operation_id IS NULL AND message_operation_state IS NULL) OR "
    "(message_operation_id IS NOT NULL AND message_operation_state IS NOT NULL AND "
    "((kind='message.confirmed' AND message_operation_state='confirmed') OR "
    "(kind='message.cancelled' AND message_operation_state='cancelled')) AND goal_id IS NULL "
    "AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND "
    "onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL "
    "AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND "
    "block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND "
    "private_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS "
    "NULL AND connection_request_version IS NULL AND connection_request_state IS NULL AND "
    "connection_request_recipient_id IS NULL AND request_view_ack_id IS NULL AND "
    "request_initiator_id IS NULL)) AND conversation_read_id IS NULL AND read_conversation_id"
    " IS NULL) OR (kind='conversation.read_acknowledged' AND conversation_read_id IS NOT NULL"
    " AND read_conversation_id IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND "
    "profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND "
    "topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND "
    "ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND "
    "report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND "
    "blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND "
    "private_passed IS NULL AND connection_request_id IS NULL AND connection_request_version "
    "IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS NULL"
    " AND message_operation_id IS NULL AND message_operation_state IS NULL AND "
    "request_view_ack_id IS NULL AND request_initiator_id IS NULL)) AND goal_share_id IS NULL"
    " AND goal_share_context_version IS NULL AND goal_share_conversation_id IS NULL) OR "
    "(kind='conversation.goal_shared' AND goal_share_id IS NOT NULL AND "
    "goal_share_context_version IS NOT NULL AND goal_share_conversation_id IS NOT NULL AND "
    "goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND "
    "block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND "
    "private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND "
    "connection_request_id IS NULL AND connection_request_version IS NULL AND "
    "connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND "
    "conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id "
    "IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND "
    "request_initiator_id IS NULL)) AND operator_audit_id IS NULL AND operator_access_version"
    " IS NULL AND operator_action IS NULL) OR (kind='operator.inspected' AND "
    "operator_audit_id IS NOT NULL AND operator_access_version IS NOT NULL AND "
    "operator_action IS NOT NULL AND operator_action IN "
    "('search_accounts','read_account','read_conversation_messages') AND goal_id IS NULL AND "
    "goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND "
    "subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND "
    "onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL "
    "AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS NULL AND "
    "block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL AND "
    "private_pass_version IS NULL AND private_passed IS NULL AND connection_request_id IS "
    "NULL AND connection_request_version IS NULL AND connection_request_state IS NULL AND "
    "connection_request_recipient_id IS NULL AND goal_share_id IS NULL AND "
    "goal_share_conversation_id IS NULL AND goal_share_context_version IS NULL AND "
    "conversation_read_id IS NULL AND read_conversation_id IS NULL AND message_operation_id "
    "IS NULL AND message_operation_state IS NULL AND request_view_ack_id IS NULL AND "
    "request_initiator_id IS NULL)) AND study_outcome_id IS NULL AND study_conversation_id IS"
    " NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS"
    " NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id "
    "IS NULL AND study_prompt_conversation_id IS NULL) OR (kind='study.reported' AND "
    "study_outcome_id IS NOT NULL AND study_conversation_id IS NOT NULL AND "
    "study_outcome_version IS NOT NULL AND study_answer IS NOT NULL AND peer_feedback_id IS "
    "NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND study_prompt_id IS"
    " NULL AND study_prompt_conversation_id IS NULL AND study_answer IN "
    "('yes','not_yet','did_not_work_out') AND goal_id IS NULL AND goal_version IS NULL AND "
    "profile_version IS NULL AND visibility_version IS NULL AND subject_id IS NULL AND "
    "topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL AND "
    "ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND "
    "report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND "
    "blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND "
    "private_passed IS NULL AND connection_request_id IS NULL AND connection_request_version "
    "IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS NULL"
    " AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND "
    "goal_share_context_version IS NULL AND conversation_read_id IS NULL AND "
    "read_conversation_id IS NULL AND message_operation_id IS NULL AND "
    "message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id"
    " IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND "
    "operator_action IS NULL) OR (kind='feedback.saved' AND study_outcome_id IS NULL AND "
    "study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS NULL"
    " AND peer_feedback_id IS NOT NULL AND peer_feedback_version IS NOT NULL AND "
    "feedback_again IS NOT NULL AND study_prompt_id IS NULL AND study_prompt_conversation_id "
    "IS NULL AND feedback_again IN ('yes','maybe','no') AND goal_id IS NULL AND goal_version "
    "IS NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id IS "
    "NULL AND topic_present IS NULL AND shared_learning IS NULL AND onboarding_task IS NULL "
    "AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND"
    " report_id IS NULL AND block_relationship_id IS NULL AND block_version IS NULL AND "
    "blocked IS NULL AND private_pass_id IS NULL AND private_pass_version IS NULL AND "
    "private_passed IS NULL AND connection_request_id IS NULL AND connection_request_version "
    "IS NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS NULL"
    " AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND "
    "goal_share_context_version IS NULL AND conversation_read_id IS NULL AND "
    "read_conversation_id IS NULL AND message_operation_id IS NULL AND "
    "message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id"
    " IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND "
    "operator_action IS NULL) OR (kind='study.prompt_offered' AND study_outcome_id IS NULL "
    "AND study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer IS "
    "NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND feedback_again "
    "IS NULL AND study_prompt_id IS NOT NULL AND study_prompt_conversation_id IS NOT NULL AND"
    " TRUE AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND "
    "block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND "
    "private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND "
    "connection_request_id IS NULL AND connection_request_version IS NULL AND "
    "connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND "
    "goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND "
    "goal_share_context_version IS NULL AND conversation_read_id IS NULL AND "
    "read_conversation_id IS NULL AND message_operation_id IS NULL AND "
    "message_operation_state IS NULL AND request_view_ack_id IS NULL AND request_initiator_id"
    " IS NULL AND operator_audit_id IS NULL AND operator_access_version IS NULL AND "
    "operator_action IS NULL)"
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_messages_owned_conversation_author", "messages", ["id", "conversation_id", "author_id"]
    )
    op.create_table(
        "peer_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("current_removal_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("current_version > 0", name=op.f("ck_peer_feedback_positive_revision")),
        sa.CheckConstraint(
            "low_id < high_id AND ((reviewer_id=low_id AND partner_id=high_id) OR "
            "(reviewer_id=high_id AND partner_id=low_id))",
            name=op.f("ck_peer_feedback_ordered_participants"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            name=op.f("fk_peer_feedback_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_removal_id", "id"],
            ["peer_feedback_removals.id", "peer_feedback_removals.feedback_id"],
            name="fk_peer_feedback_current_removal",
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["id", "current_version"],
            ["peer_feedback_revisions.feedback_id", "peer_feedback_revisions.version"],
            name="fk_peer_feedback_current",
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["accounts.id"],
            name=op.f("fk_peer_feedback_partner_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["accounts.id"],
            name=op.f("fk_peer_feedback_reviewer_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_peer_feedback")),
        sa.UniqueConstraint(
            "id",
            "conversation_id",
            "reviewer_id",
            "partner_id",
            "low_id",
            "high_id",
            name="uq_peer_feedback_owned_source",
        ),
        sa.UniqueConstraint("reviewer_id", "partner_id", name="uq_peer_feedback_ordered_pair"),
    )
    op.create_index(
        "ix_peer_feedback_partner", "peer_feedback", ["partner_id", "reviewer_id"], unique=False
    )
    op.create_table(
        "study_outcomes",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.CheckConstraint("current_version > 0", name=op.f("ck_study_outcomes_positive_revision")),
        sa.CheckConstraint(
            "low_id < high_id AND actor_id IN (low_id,high_id)",
            name=op.f("ck_study_outcomes_participant_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_study_outcomes_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "actor_id", "current_version"],
            [
                "study_outcome_revisions.conversation_id",
                "study_outcome_revisions.actor_id",
                "study_outcome_revisions.version",
            ],
            name="fk_study_outcomes_current",
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            name=op.f("fk_study_outcomes_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("conversation_id", "actor_id", name=op.f("pk_study_outcomes")),
        sa.UniqueConstraint(
            "conversation_id",
            "actor_id",
            "low_id",
            "high_id",
            name="uq_study_outcomes_participants",
        ),
    )
    op.create_table(
        "study_prompt_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND "
            "span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != "
            "repeat('0',32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != "
            "repeat('0',16))",
            name=op.f("ck_study_prompt_receipts_origin_trace_pair"),
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND"
            " span_id IS NULL)",
            name=op.f("ck_study_prompt_receipts_origin_request_context"),
        ),
        sa.CheckConstraint(
            "low_id < high_id AND actor_id IN (low_id,high_id)",
            name=op.f("ck_study_prompt_receipts_participant_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_study_prompt_receipts_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            name=op.f("fk_study_prompt_receipts_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_study_prompt_receipts")),
        sa.UniqueConstraint("actor_id", "conversation_id", name="uq_study_prompt_receipts_once"),
        sa.UniqueConstraint(
            "id", "conversation_id", "actor_id", name="uq_study_prompt_receipts_event_source"
        ),
    )
    op.create_table(
        "study_outcome_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("answer", sa.String(length=20), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND "
            "span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != "
            "repeat('0',32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != "
            "repeat('0',16))",
            name=op.f("ck_study_outcome_revisions_origin_trace_pair"),
        ),
        sa.CheckConstraint(
            "answer IN ('yes','not_yet','did_not_work_out')",
            name=op.f("ck_study_outcome_revisions_bounded_answer"),
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND"
            " span_id IS NULL)",
            name=op.f("ck_study_outcome_revisions_origin_request_context"),
        ),
        sa.CheckConstraint(
            "version > 0", name=op.f("ck_study_outcome_revisions_positive_revision")
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "actor_id", "low_id", "high_id"],
            [
                "study_outcomes.conversation_id",
                "study_outcomes.actor_id",
                "study_outcomes.low_id",
                "study_outcomes.high_id",
            ],
            name=op.f("fk_study_outcome_revisions_conversation_id_study_outcomes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_study_outcome_revisions")),
        sa.UniqueConstraint(
            "conversation_id", "actor_id", "version", name="uq_study_outcome_revisions_version"
        ),
        sa.UniqueConstraint(
            "id",
            "conversation_id",
            "actor_id",
            "answer",
            name="uq_study_outcome_revisions_worked_source",
        ),
        sa.UniqueConstraint(
            "id",
            "conversation_id",
            "actor_id",
            "version",
            "answer",
            name="uq_study_outcome_revisions_event_source",
        ),
        sa.UniqueConstraint(
            "id", "conversation_id", "actor_id", name="uq_study_outcome_revisions_owned"
        ),
    )
    op.create_index(
        "ix_study_outcome_revisions_window",
        "study_outcome_revisions",
        ["conversation_id", "actor_id", "changed_at", "version"],
        unique=False,
    )
    op.create_table(
        "peer_feedback_revisions",
        sa.Column("feedback_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("worked_confirmation_id", sa.Uuid(), nullable=False),
        sa.Column("worked_answer", sa.String(length=20), nullable=False),
        sa.Column("low_message_id", sa.Uuid(), nullable=True),
        sa.Column("high_message_id", sa.Uuid(), nullable=True),
        sa.Column("again", sa.String(length=5), nullable=False),
        sa.Column("descriptors", sa.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("team_note", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND "
            "span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != "
            "repeat('0',32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != "
            "repeat('0',16))",
            name=op.f("ck_peer_feedback_revisions_origin_trace_pair"),
        ),
        sa.CheckConstraint(
            "again IN ('yes','maybe','no')", name=op.f("ck_peer_feedback_revisions_bounded_again")
        ),
        sa.CheckConstraint(
            "cardinality(descriptors) <= 3 AND (array_ndims(descriptors)=1 OR "
            "cardinality(descriptors)=0) AND array_position(descriptors,NULL) IS NULL "
            "AND descriptors <@ "
            "ARRAY['easy_to_communicate','prepared','supportive']::varchar[] AND "
            "cardinality(array_positions(descriptors,'easy_to_communicate'))<=1 AND "
            "cardinality(array_positions(descriptors,'prepared'))<=1 AND "
            "cardinality(array_positions(descriptors,'supportive'))<=1",
            name=op.f("ck_peer_feedback_revisions_bounded_unique_descriptors"),
        ),
        sa.CheckConstraint(
            "team_note IS NULL OR (length(team_note) BETWEEN 1 AND 1000 AND team_note ~"
            " '[^[:space:]]')",
            name=op.f("ck_peer_feedback_revisions_bounded_team_note"),
        ),
        sa.CheckConstraint(
            "worked_answer='yes'", name=op.f("ck_peer_feedback_revisions_explicit_worked_yes")
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND"
            " span_id IS NULL)",
            name=op.f("ck_peer_feedback_revisions_origin_request_context"),
        ),
        sa.CheckConstraint(
            "low_message_id IS NULL OR high_message_id IS NULL OR low_message_id != "
            "high_message_id",
            name=op.f("ck_peer_feedback_revisions_distinct_human_messages"),
        ),
        sa.CheckConstraint(
            "version > 0", name=op.f("ck_peer_feedback_revisions_positive_revision")
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id", "conversation_id", "reviewer_id", "partner_id", "low_id", "high_id"],
            [
                "peer_feedback.id",
                "peer_feedback.conversation_id",
                "peer_feedback.reviewer_id",
                "peer_feedback.partner_id",
                "peer_feedback.low_id",
                "peer_feedback.high_id",
            ],
            name=op.f("fk_peer_feedback_revisions_feedback_id_peer_feedback"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["high_message_id", "conversation_id", "high_id"],
            ["messages.id", "messages.conversation_id", "messages.author_id"],
            name="fk_peer_feedback_high_human",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["low_message_id", "conversation_id", "low_id"],
            ["messages.id", "messages.conversation_id", "messages.author_id"],
            name="fk_peer_feedback_low_human",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["worked_confirmation_id", "conversation_id", "reviewer_id", "worked_answer"],
            [
                "study_outcome_revisions.id",
                "study_outcome_revisions.conversation_id",
                "study_outcome_revisions.actor_id",
                "study_outcome_revisions.answer",
            ],
            name=op.f("fk_peer_feedback_revisions_worked_confirmation_id_study_outcome_revisions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("feedback_id", "version", name=op.f("pk_peer_feedback_revisions")),
        sa.UniqueConstraint(
            "feedback_id",
            "version",
            "reviewer_id",
            "again",
            name="uq_peer_feedback_revisions_event_source",
        ),
        sa.UniqueConstraint(
            "feedback_id",
            "version",
            "reviewer_id",
            "conversation_id",
            name="uq_peer_feedback_revisions_intent_source",
        ),
        sa.UniqueConstraint(
            "feedback_id", "version", "reviewer_id", name="uq_peer_feedback_revisions_owned"
        ),
    )
    op.create_table(
        "feedback_command_intents",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_kind", sa.String(length=12), nullable=False),
        sa.Column("outcome_id", sa.Uuid(), nullable=True),
        sa.Column("feedback_id", sa.Uuid(), nullable=True),
        sa.Column("feedback_version", sa.Integer(), nullable=True),
        sa.Column("prompt_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(operation='study_outcome' AND result_kind='outcome' AND outcome_id IS NOT"
            " NULL AND feedback_id IS NULL AND feedback_version IS NULL AND prompt_id "
            "IS NULL) OR (operation='assessment' AND result_kind='assessment' AND "
            "feedback_id IS NOT NULL AND feedback_version IS NOT NULL AND "
            "feedback_version > 0 AND outcome_id IS NULL AND prompt_id IS NULL) OR "
            "(operation='prompt_visit' AND result_kind='prompt' AND prompt_id IS NOT "
            "NULL AND outcome_id IS NULL AND feedback_id IS NULL AND feedback_version "
            "IS NULL) OR (operation='prompt_visit' AND result_kind='no_offer' AND "
            "prompt_id IS NULL AND outcome_id IS NULL AND feedback_id IS NULL AND "
            "feedback_version IS NULL)",
            name=op.f("ck_feedback_command_intents_typed_result"),
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'", name=op.f("ck_feedback_command_intents_bounded_key")
        ),
        sa.CheckConstraint(
            "low_id < high_id AND actor_id IN (low_id,high_id)",
            name=op.f("ck_feedback_command_intents_participant_actor"),
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint)=32",
            name=op.f("ck_feedback_command_intents_fingerprint_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_feedback_command_intents_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            name=op.f("fk_feedback_command_intents_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id", "feedback_version", "actor_id", "conversation_id"],
            [
                "peer_feedback_revisions.feedback_id",
                "peer_feedback_revisions.version",
                "peer_feedback_revisions.reviewer_id",
                "peer_feedback_revisions.conversation_id",
            ],
            name=op.f("fk_feedback_command_intents_feedback_id_peer_feedback_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["outcome_id", "conversation_id", "actor_id"],
            [
                "study_outcome_revisions.id",
                "study_outcome_revisions.conversation_id",
                "study_outcome_revisions.actor_id",
            ],
            name="fk_feedback_intents_outcome",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id", "conversation_id", "actor_id"],
            [
                "study_prompt_receipts.id",
                "study_prompt_receipts.conversation_id",
                "study_prompt_receipts.actor_id",
            ],
            name=op.f("fk_feedback_command_intents_prompt_id_study_prompt_receipts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "actor_id", "operation", "key", name=op.f("pk_feedback_command_intents")
        ),
    )
    op.create_table(
        "peer_feedback_removals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("feedback_id", sa.Uuid(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("operator_access_version", sa.Integer(), nullable=False),
        sa.Column("operator_access_active", sa.Boolean(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND "
            "span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != "
            "repeat('0',32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != "
            "repeat('0',16))",
            name=op.f("ck_peer_feedback_removals_origin_trace_pair"),
        ),
        sa.CheckConstraint(
            "kind IN ('fraudulent','abusive')", name=op.f("ck_peer_feedback_removals_bounded_kind")
        ),
        sa.CheckConstraint(
            "length(reason) BETWEEN 1 AND 1000 AND reason ~ '[^[:space:]]'",
            name=op.f("ck_peer_feedback_removals_bounded_reason"),
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND"
            " span_id IS NULL)",
            name=op.f("ck_peer_feedback_removals_origin_request_context"),
        ),
        sa.CheckConstraint(
            "operator_access_active", name=op.f("ck_peer_feedback_removals_active_operator_source")
        ),
        sa.CheckConstraint(
            "source_version > 0 AND operator_access_version > 0",
            name=op.f("ck_peer_feedback_removals_positive_source_revisions"),
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id", "source_version"],
            ["peer_feedback_revisions.feedback_id", "peer_feedback_revisions.version"],
            name=op.f("fk_peer_feedback_removals_feedback_id_peer_feedback_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            name=op.f("fk_peer_feedback_removals_operator_id_operator_access_revisions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_peer_feedback_removals")),
        sa.UniqueConstraint("id", "feedback_id", name="uq_peer_feedback_removals_owned"),
    )
    op.add_column("product_events", sa.Column("study_outcome_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("study_conversation_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("study_outcome_version", sa.Integer(), nullable=True))
    op.add_column("product_events", sa.Column("study_answer", sa.String(length=32), nullable=True))
    op.add_column("product_events", sa.Column("peer_feedback_id", sa.Uuid(), nullable=True))
    op.add_column("product_events", sa.Column("peer_feedback_version", sa.Integer(), nullable=True))
    op.add_column(
        "product_events", sa.Column("feedback_again", sa.String(length=16), nullable=True)
    )
    op.add_column("product_events", sa.Column("study_prompt_id", sa.Uuid(), nullable=True))
    op.add_column(
        "product_events", sa.Column("study_prompt_conversation_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_product_events_study_prompt_source",
        "product_events",
        "study_prompt_receipts",
        ["study_prompt_id", "study_prompt_conversation_id", "account_id"],
        ["id", "conversation_id", "actor_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_product_events_peer_feedback_source",
        "product_events",
        "peer_feedback_revisions",
        ["peer_feedback_id", "peer_feedback_version", "account_id", "feedback_again"],
        ["feedback_id", "version", "reviewer_id", "again"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_product_events_study_outcome_source",
        "product_events",
        "study_outcome_revisions",
        [
            "study_outcome_id",
            "study_conversation_id",
            "account_id",
            "study_outcome_version",
            "study_answer",
        ],
        ["id", "conversation_id", "actor_id", "version", "answer"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_study_outcomes_current",
        "study_outcomes",
        "study_outcome_revisions",
        ["conversation_id", "actor_id", "current_version"],
        ["conversation_id", "actor_id", "version"],
        ondelete="RESTRICT",
        initially="DEFERRED",
        deferrable=True,
    )
    op.create_foreign_key(
        "fk_peer_feedback_current",
        "peer_feedback",
        "peer_feedback_revisions",
        ["id", "current_version"],
        ["feedback_id", "version"],
        ondelete="RESTRICT",
        initially="DEFERRED",
        deferrable=True,
    )
    op.create_foreign_key(
        "fk_peer_feedback_current_removal",
        "peer_feedback",
        "peer_feedback_removals",
        ["current_removal_id", "id"],
        ["id", "feedback_id"],
        ondelete="RESTRICT",
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", EVENT_SHAPE
    )


def downgrade() -> None:
    retained = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM study_outcomes) OR EXISTS (SELECT 1 FROM "
                "peer_feedback) OR EXISTS (SELECT 1 FROM study_prompt_receipts) OR EXISTS "
                "(SELECT 1 FROM feedback_command_intents)"
            )
        )
        .scalar_one()
    )
    if retained:
        raise RuntimeError("Cannot remove retained study reports, feedback or prompt history")
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", PREVIOUS_EVENT_SHAPE
    )
    op.drop_constraint("fk_peer_feedback_current_removal", "peer_feedback", type_="foreignkey")
    op.drop_constraint("fk_peer_feedback_current", "peer_feedback", type_="foreignkey")
    op.drop_constraint("fk_study_outcomes_current", "study_outcomes", type_="foreignkey")
    op.drop_constraint(
        "fk_product_events_study_outcome_source", "product_events", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_product_events_peer_feedback_source", "product_events", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_product_events_study_prompt_source", "product_events", type_="foreignkey"
    )
    op.drop_column("product_events", "study_prompt_conversation_id")
    op.drop_column("product_events", "study_prompt_id")
    op.drop_column("product_events", "feedback_again")
    op.drop_column("product_events", "peer_feedback_version")
    op.drop_column("product_events", "peer_feedback_id")
    op.drop_column("product_events", "study_answer")
    op.drop_column("product_events", "study_outcome_version")
    op.drop_column("product_events", "study_conversation_id")
    op.drop_column("product_events", "study_outcome_id")
    op.drop_table("peer_feedback_removals")
    op.drop_table("feedback_command_intents")
    op.drop_table("peer_feedback_revisions")
    op.drop_index("ix_study_outcome_revisions_window", table_name="study_outcome_revisions")
    op.drop_table("study_outcome_revisions")
    op.drop_table("study_prompt_receipts")
    op.drop_table("study_outcomes")
    op.drop_index("ix_peer_feedback_partner", table_name="peer_feedback")
    op.drop_table("peer_feedback")
    op.drop_constraint("uq_messages_owned_conversation_author", "messages", type_="unique")
