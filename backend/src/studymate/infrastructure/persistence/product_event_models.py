"""Typed retained canonical outcomes, with no arbitrary payload/content column."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base

_PREVIOUS_REFERENCE_SHAPE: str = (
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

_BEFORE_REQUEST_REFERENCE_SHAPE: str = (
    f"(({_PREVIOUS_REFERENCE_SHAPE}) AND private_pass_id IS NULL "
    "AND private_pass_version IS NULL AND private_passed IS NULL) OR "
    "(kind = 'discovery.pass_changed' AND private_pass_id IS NOT NULL "
    "AND private_pass_version IS NOT NULL AND private_passed IS NOT NULL "
    "AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL "
    "AND visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL "
    "AND shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL "
    "AND ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL "
    "AND report_id IS NULL AND block_relationship_id IS NULL "
    "AND block_version IS NULL AND blocked IS NULL)"
)

_BEFORE_VIEW_REFERENCE_SHAPE: str = (
    f"(({_BEFORE_REQUEST_REFERENCE_SHAPE}) AND connection_request_id IS NULL "
    "AND connection_request_version IS NULL AND connection_request_state IS NULL "
    "AND connection_request_recipient_id IS NULL AND request_initiator_id IS NULL) OR "
    "(kind = 'request.changed' AND connection_request_id IS NOT NULL "
    "AND connection_request_version IS NOT NULL AND connection_request_state IS NOT NULL "
    "AND connection_request_recipient_id IS NOT NULL "
    "AND (request_initiator_id IS NULL OR request_initiator_id IN "
    "(account_id, connection_request_recipient_id)) AND goal_id IS NULL "
    "AND goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL "
    "AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL "
    "AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL "
    "AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL "
    "AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL "
    "AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL)"
)


_BEFORE_MESSAGE_REFERENCE_SHAPE: str = (
    f"(({_BEFORE_VIEW_REFERENCE_SHAPE}) AND request_view_ack_id IS NULL) OR "
    "(kind = 'request.view_acknowledged' AND request_view_ack_id IS NOT NULL AND "
    "goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND "
    "block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND "
    "private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND "
    "connection_request_id IS NULL AND connection_request_version IS NULL AND "
    "connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND "
    "request_initiator_id IS NULL"
    ")"
)


_BEFORE_READ_REFERENCE_SHAPE: str = (
    f"(({_BEFORE_MESSAGE_REFERENCE_SHAPE}) AND message_operation_id IS NULL "
    "AND message_operation_state IS NULL) OR (message_operation_id IS NOT NULL "
    "AND message_operation_state IS NOT NULL AND ((kind='message.confirmed' "
    "AND message_operation_state='confirmed') OR (kind='message.cancelled' "
    "AND message_operation_state='cancelled')) AND "
    "goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND "
    "block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND "
    "private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND "
    "connection_request_id IS NULL AND connection_request_version IS NULL AND "
    "connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND "
    "request_view_ack_id IS NULL AND request_initiator_id IS NULL"
    ")"
)


_BEFORE_SHARE_REFERENCE_SHAPE: str = (
    f"(({_BEFORE_READ_REFERENCE_SHAPE}) AND conversation_read_id IS NULL "
    "AND read_conversation_id IS NULL) OR (kind='conversation.read_acknowledged' "
    "AND conversation_read_id IS NOT NULL AND read_conversation_id IS NOT NULL AND "
    "goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS"
    " NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL AND "
    "block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL AND "
    "private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed IS NULL AND "
    "connection_request_id IS NULL AND connection_request_version IS NULL AND "
    "connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND "
    "message_operation_id IS NULL AND message_operation_state IS NULL AND request_view_ack_id"
    " IS NULL AND request_initiator_id IS NULL"
    ")"
)


_BEFORE_OPERATOR_REFERENCE_SHAPE: str = (
    f"(({_BEFORE_SHARE_REFERENCE_SHAPE}) AND goal_share_id IS NULL "
    "AND goal_share_context_version IS NULL AND goal_share_conversation_id IS NULL) OR "
    "(kind='conversation.goal_shared' AND goal_share_id IS NOT NULL "
    "AND goal_share_context_version IS NOT NULL AND goal_share_conversation_id IS NOT NULL AND "
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
    "request_initiator_id IS NULL"
    ")"
)


_BEFORE_FEEDBACK_REFERENCE_SHAPE: str = (
    f"(({_BEFORE_OPERATOR_REFERENCE_SHAPE}) AND operator_audit_id IS NULL "
    "AND operator_access_version IS NULL AND operator_action IS NULL) OR "
    "(kind='operator.inspected' AND operator_audit_id IS NOT NULL "
    "AND operator_access_version IS NOT NULL AND operator_action IS NOT NULL "
    "AND operator_action IN ('search_accounts','read_account','read_conversatio"
    "n_messages','search_events','read_event','read_audit','search_reports','read_rep"
    "ort','read_media') AND "
    "goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
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
    " IS NULL"
    ")"
)


LEGACY_EVENT_REFERENCE_SHAPE: str = (
    f"(({_BEFORE_FEEDBACK_REFERENCE_SHAPE})"
    " AND study_outcome_id IS NULL AND study_conversation_id IS NULL AND "
    "study_outcome_version IS NULL AND study_answer IS NULL AND peer_feedback_id IS "
    "NULL AND peer_feedback_version IS NULL AND feedback_again IS NULL AND "
    "study_prompt_id IS NULL AND study_prompt_conversation_id IS NULL) OR "
    "(kind='study.reported' AND study_outcome_id IS NOT NULL AND "
    "study_conversation_id IS NOT NULL AND study_outcome_version IS NOT NULL AND "
    "study_answer IS NOT NULL AND peer_feedback_id IS NULL AND peer_feedback_version "
    "IS NULL AND feedback_again IS NULL AND study_prompt_id IS NULL AND "
    "study_prompt_conversation_id IS NULL AND study_answer IN "
    "('yes','not_yet','did_not_work_out') AND goal_id IS NULL AND goal_version IS "
    "NULL AND profile_version IS NULL AND visibility_version IS NULL AND subject_id "
    "IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND "
    "onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state "
    "IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS"
    " NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL "
    "AND private_pass_version IS NULL AND private_passed IS NULL AND "
    "connection_request_id IS NULL AND connection_request_version IS NULL AND "
    "connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND"
    " goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND "
    "goal_share_context_version IS NULL AND conversation_read_id IS NULL AND "
    "read_conversation_id IS NULL AND message_operation_id IS NULL AND "
    "message_operation_state IS NULL AND request_view_ack_id IS NULL AND "
    "request_initiator_id IS NULL AND operator_audit_id IS NULL AND "
    "operator_access_version IS NULL AND operator_action IS NULL) OR "
    "(kind='feedback.saved' AND study_outcome_id IS NULL AND study_conversation_id IS"
    " NULL AND study_outcome_version IS NULL AND study_answer IS NULL AND "
    "peer_feedback_id IS NOT NULL AND peer_feedback_version IS NOT NULL AND "
    "feedback_again IS NOT NULL AND study_prompt_id IS NULL AND "
    "study_prompt_conversation_id IS NULL AND feedback_again IN ('yes','maybe','no') "
    "AND goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND subject_id IS NULL AND topic_present IS NULL AND "
    "shared_learning IS NULL AND onboarding_task IS NULL AND ai_job_id IS NULL AND "
    "ai_kind IS NULL AND ai_state IS NULL AND ai_reason IS NULL AND report_id IS NULL"
    " AND block_relationship_id IS NULL AND block_version IS NULL AND blocked IS NULL"
    " AND private_pass_id IS NULL AND private_pass_version IS NULL AND private_passed"
    " IS NULL AND connection_request_id IS NULL AND connection_request_version IS "
    "NULL AND connection_request_state IS NULL AND connection_request_recipient_id IS"
    " NULL AND goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND "
    "goal_share_context_version IS NULL AND conversation_read_id IS NULL AND "
    "read_conversation_id IS NULL AND message_operation_id IS NULL AND "
    "message_operation_state IS NULL AND request_view_ack_id IS NULL AND "
    "request_initiator_id IS NULL AND operator_audit_id IS NULL AND "
    "operator_access_version IS NULL AND operator_action IS NULL) OR "
    "(kind='study.prompt_offered' AND study_outcome_id IS NULL AND "
    "study_conversation_id IS NULL AND study_outcome_version IS NULL AND study_answer"
    " IS NULL AND peer_feedback_id IS NULL AND peer_feedback_version IS NULL AND "
    "feedback_again IS NULL AND study_prompt_id IS NOT NULL AND "
    "study_prompt_conversation_id IS NOT NULL AND TRUE AND goal_id IS NULL AND "
    "goal_version IS NULL AND profile_version IS NULL AND visibility_version IS NULL "
    "AND subject_id IS NULL AND topic_present IS NULL AND shared_learning IS NULL AND"
    " onboarding_task IS NULL AND ai_job_id IS NULL AND ai_kind IS NULL AND ai_state "
    "IS NULL AND ai_reason IS NULL AND report_id IS NULL AND block_relationship_id IS"
    " NULL AND block_version IS NULL AND blocked IS NULL AND private_pass_id IS NULL "
    "AND private_pass_version IS NULL AND private_passed IS NULL AND "
    "connection_request_id IS NULL AND connection_request_version IS NULL AND "
    "connection_request_state IS NULL AND connection_request_recipient_id IS NULL AND"
    " goal_share_id IS NULL AND goal_share_conversation_id IS NULL AND "
    "goal_share_context_version IS NULL AND conversation_read_id IS NULL AND "
    "read_conversation_id IS NULL AND message_operation_id IS NULL AND "
    "message_operation_state IS NULL AND request_view_ack_id IS NULL AND "
    "request_initiator_id IS NULL AND operator_audit_id IS NULL AND "
    "operator_access_version IS NULL AND operator_action IS NULL)"
)


_REVISION_SOURCE_COLUMNS = (
    "goal_id",
    "goal_version",
    "profile_version",
    "visibility_version",
    "subject_id",
    "topic_present",
    "shared_learning",
    "onboarding_task",
    "ai_job_id",
    "ai_kind",
    "ai_state",
    "ai_reason",
    "report_id",
    "block_relationship_id",
    "block_version",
    "blocked",
    "private_pass_id",
    "private_pass_version",
    "private_passed",
    "connection_request_id",
    "connection_request_version",
    "connection_request_state",
    "connection_request_recipient_id",
    "goal_share_id",
    "goal_share_conversation_id",
    "goal_share_context_version",
    "conversation_read_id",
    "read_conversation_id",
    "message_operation_id",
    "message_operation_state",
    "request_view_ack_id",
    "request_initiator_id",
    "operator_audit_id",
    "operator_access_version",
    "operator_action",
    "study_outcome_id",
    "study_conversation_id",
    "study_outcome_version",
    "study_answer",
    "peer_feedback_id",
    "peer_feedback_version",
    "feedback_again",
    "study_prompt_id",
    "study_prompt_conversation_id",
    "help_version",
    "photo_version",
)
_REVISION_EVENT_REFERENCES = (
    ("profile.saved", "profile_version"),
    ("help.saved", "help_version"),
    ("photo.published", "photo_version"),
)
_REVISION_EVENT_SHAPES = tuple(
    f"kind='{kind}' AND {reference} IS NOT NULL AND "
    + " AND ".join(
        f"{column} IS NULL" for column in _REVISION_SOURCE_COLUMNS if column != reference
    )
    for kind, reference in _REVISION_EVENT_REFERENCES
)
_ACADEMIC_EVENT_REFERENCE_SHAPE = (
    f"(({LEGACY_EVENT_REFERENCE_SHAPE}) AND help_version IS NULL AND photo_version IS NULL)"
    " OR (" + ") OR (".join(_REVISION_EVENT_SHAPES) + ")"
)


_LIFECYCLE_SOURCE_COLUMNS = (
    "lifecycle_revision_id",
    "lifecycle_account_id",
    "lifecycle_version",
    "lifecycle_operation",
)
EVENT_REFERENCE_SHAPE = (
    f"(({_ACADEMIC_EVENT_REFERENCE_SHAPE}) AND "
    + " AND ".join(f"{column} IS NULL" for column in _LIFECYCLE_SOURCE_COLUMNS)
    + ") OR (kind='account.lifecycle_changed' AND lifecycle_revision_id IS NOT NULL "
    "AND lifecycle_account_id IS NOT NULL AND lifecycle_version IS NOT NULL "
    "AND lifecycle_version>0 AND lifecycle_operation IS NOT NULL "
    "AND lifecycle_operation IN ('ban','unban','delete') AND "
    + " AND ".join(f"{column} IS NULL" for column in _REVISION_SOURCE_COLUMNS)
    + ")"
)


BEFORE_STUDENT_SUPPORT_EVENT_REFERENCE_SHAPE = EVENT_REFERENCE_SHAPE
_SUPPORT_LEGACY_SHAPE = EVENT_REFERENCE_SHAPE.replace(
    "'read_media')", "'read_media','read_support_case')"
)
_SUPPORT_NULL_LEGACY_REFERENCES = " AND ".join(
    f"{column} IS NULL" for column in (*_REVISION_SOURCE_COLUMNS, *_LIFECYCLE_SOURCE_COLUMNS)
)
EVENT_REFERENCE_SHAPE = (
    f"(({_SUPPORT_LEGACY_SHAPE}) AND notification_preference_version IS NULL "
    "AND support_case_id IS NULL AND support_case_version IS NULL) OR "
    "(kind='notification_preference.changed' AND notification_preference_version "
    "IS NOT NULL AND notification_preference_version>0 AND support_case_id IS NULL "
    f"AND support_case_version IS NULL AND {_SUPPORT_NULL_LEGACY_REFERENCES}) OR "
    "(kind IN ('support.received','support.status_changed') AND support_case_id IS "
    "NOT NULL AND support_case_version IS NOT NULL AND support_case_version>0 "
    "AND notification_preference_version IS NULL AND "
    f"{_SUPPORT_NULL_LEGACY_REFERENCES})"
)


EVENT_REFERENCE_SHAPE = EVENT_REFERENCE_SHAPE.replace(
    "'read_support_case')", "'read_support_case','search_support_cases')"
)


EVENT_REFERENCE_SHAPE = EVENT_REFERENCE_SHAPE.replace(
    "'read_support_case','search_support_cases')",
    "'read_support_case','search_support_cases','search_delivery_sources','read_delivery_source')",
)


EVENT_REFERENCE_SHAPE = EVENT_REFERENCE_SHAPE.replace(
    "'search_delivery_sources','read_delivery_source')",
    "'search_delivery_sources','read_delivery_source','read_chat_media')",
)


EVENT_REFERENCE_SHAPE = EVENT_REFERENCE_SHAPE.replace(
    "'read_chat_media')", "'read_chat_media','search_audits')"
)


class ProductEventRecord(Base):
    __tablename__ = "product_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "notification_preference_version"],
            [
                "notification_preference_revisions.account_id",
                "notification_preference_revisions.version",
            ],
            name="fk_product_events_notification_preference_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["support_case_id", "support_case_version"],
            ["support_case_revisions.case_id", "support_case_revisions.version"],
            name="fk_product_events_support_revision_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "lifecycle_revision_id",
                "account_id",
                "lifecycle_account_id",
                "lifecycle_version",
                "lifecycle_operation",
            ],
            [
                "account_lifecycle_revisions.id",
                "account_lifecycle_revisions.actor_id",
                "account_lifecycle_revisions.account_id",
                "account_lifecycle_revisions.version",
                "account_lifecycle_revisions.operation",
            ],
            name="fk_product_events_lifecycle_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "study_outcome_id",
                "study_conversation_id",
                "account_id",
                "study_outcome_version",
                "study_answer",
            ],
            [
                "study_outcome_revisions.id",
                "study_outcome_revisions.conversation_id",
                "study_outcome_revisions.actor_id",
                "study_outcome_revisions.version",
                "study_outcome_revisions.answer",
            ],
            name="fk_product_events_study_outcome_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["peer_feedback_id", "peer_feedback_version", "account_id", "feedback_again"],
            [
                "peer_feedback_revisions.feedback_id",
                "peer_feedback_revisions.version",
                "peer_feedback_revisions.reviewer_id",
                "peer_feedback_revisions.again",
            ],
            name="fk_product_events_peer_feedback_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["study_prompt_id", "study_prompt_conversation_id", "account_id"],
            [
                "study_prompt_receipts.id",
                "study_prompt_receipts.conversation_id",
                "study_prompt_receipts.actor_id",
            ],
            name="fk_product_events_study_prompt_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["operator_audit_id", "account_id", "operator_access_version", "operator_action"],
            [
                "operator_audits.id",
                "operator_audits.operator_id",
                "operator_audits.operator_access_version",
                "operator_audits.action",
            ],
            name="fk_product_events_operator_audit_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "goal_share_id",
                "account_id",
                "goal_share_conversation_id",
                "goal_share_context_version",
            ],
            [
                "conversation_goal_shares.id",
                "conversation_goal_shares.owner_id",
                "conversation_goal_shares.conversation_id",
                "conversation_goal_shares.context_version",
            ],
            name="fk_product_events_goal_share_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["conversation_read_id", "account_id", "read_conversation_id"],
            [
                "conversation_read_revisions.id",
                "conversation_read_revisions.account_id",
                "conversation_read_revisions.conversation_id",
            ],
            name="fk_product_events_conversation_read_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["message_operation_id", "account_id", "message_operation_state"],
            ["message_operations.id", "message_operations.author_id", "message_operations.state"],
            name="fk_product_events_message_outcome",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["request_view_ack_id", "account_id"],
            ["request_view_acknowledgements.id", "request_view_acknowledgements.viewer_id"],
            name="fk_product_events_request_view_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["connection_request_id", "account_id", "connection_request_recipient_id"],
            [
                "connection_requests.id",
                "connection_requests.sender_id",
                "connection_requests.recipient_id",
            ],
            name="fk_product_events_request_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["connection_request_id", "connection_request_version", "connection_request_state"],
            [
                "request_revisions.request_id",
                "request_revisions.version",
                "request_revisions.state",
            ],
            name="fk_product_events_request_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["private_pass_id", "private_pass_version", "account_id", "private_passed"],
            [
                "private_pass_revisions.pass_id",
                "private_pass_revisions.version",
                "private_pass_revisions.account_id",
                "private_pass_revisions.passed",
            ],
            name="fk_product_events_private_pass_outcome",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["report_id", "account_id"],
            ["profile_reports.id", "profile_reports.reporter_id"],
            name="fk_product_events_report_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["block_relationship_id", "account_id", "block_version", "blocked"],
            [
                "block_revisions.relationship_id",
                "block_revisions.blocker_id",
                "block_revisions.version",
                "block_revisions.blocked",
            ],
            name="fk_product_events_block_outcome",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["ai_job_id", "account_id", "ai_kind"],
            ["ai_jobs.id", "ai_jobs.actor_id", "ai_jobs.kind"],
            name="fk_product_events_ai_job_owner_kind",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "account_id", "kind", "occurrence_key", name="uq_product_events_occurrence"
        ),
        ForeignKeyConstraint(
            ["account_id", "goal_id", "goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "profile_version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "help_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            name="fk_product_events_help_revision_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "photo_version"],
            ["photo_revisions.account_id", "photo_revisions.version"],
            name="fk_product_events_photo_revision_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "visibility_version"],
            ["visibility_revisions.account_id", "visibility_revisions.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("schema_version = 1", name="known_schema_version"),
        CheckConstraint("occurrence_key ~ '^[A-Za-z0-9:_-]{1,100}$'", name="occurrence_key_shape"),
        CheckConstraint(EVENT_REFERENCE_SHAPE, name="event_reference_shape"),
        CheckConstraint(
            "request_id IS NOT NULL OR "
            "(action_id IS NULL AND trace_id IS NULL AND span_id IS NULL)",
            name="origin_request_context",
        ),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR "
            "(trace_id IS NOT NULL AND span_id IS NOT NULL AND "
            "trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0', 32) AND "
            "span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))",
            name="origin_trace_pair",
        ),
        Index("ix_product_events_actor_time", "account_id", "occurred_at", "id"),
        Index("ix_product_events_kind_time", "kind", "occurred_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    lifecycle_revision_id: Mapped[UUID | None] = mapped_column()
    lifecycle_account_id: Mapped[UUID | None] = mapped_column()
    lifecycle_version: Mapped[int | None] = mapped_column()
    lifecycle_operation: Mapped[str | None] = mapped_column(String(6))
    kind: Mapped[str] = mapped_column(String(32))
    occurrence_key: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[int] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    goal_id: Mapped[UUID | None] = mapped_column()
    goal_version: Mapped[int | None] = mapped_column()
    profile_version: Mapped[int | None] = mapped_column()
    help_version: Mapped[int | None] = mapped_column()
    photo_version: Mapped[int | None] = mapped_column()
    visibility_version: Mapped[int | None] = mapped_column()
    subject_id: Mapped[UUID | None] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"))
    topic_present: Mapped[bool | None] = mapped_column()
    shared_learning: Mapped[bool | None] = mapped_column()
    onboarding_task: Mapped[str | None] = mapped_column(String(16))
    ai_job_id: Mapped[UUID | None] = mapped_column()
    ai_kind: Mapped[str | None] = mapped_column(String(24))
    ai_state: Mapped[str | None] = mapped_column(String(16))
    ai_reason: Mapped[str | None] = mapped_column(String(32))
    report_id: Mapped[UUID | None] = mapped_column()
    block_relationship_id: Mapped[UUID | None] = mapped_column()
    block_version: Mapped[int | None] = mapped_column()
    blocked: Mapped[bool | None] = mapped_column()
    private_pass_id: Mapped[UUID | None] = mapped_column()
    private_pass_version: Mapped[int | None] = mapped_column()
    private_passed: Mapped[bool | None] = mapped_column()
    connection_request_id: Mapped[UUID | None] = mapped_column()
    connection_request_version: Mapped[int | None] = mapped_column()
    connection_request_state: Mapped[str | None] = mapped_column(String(24))
    connection_request_recipient_id: Mapped[UUID | None] = mapped_column()
    goal_share_id: Mapped[UUID | None] = mapped_column()
    goal_share_conversation_id: Mapped[UUID | None] = mapped_column()
    goal_share_context_version: Mapped[int | None] = mapped_column(BigInteger)
    conversation_read_id: Mapped[UUID | None] = mapped_column()
    read_conversation_id: Mapped[UUID | None] = mapped_column()
    message_operation_id: Mapped[UUID | None] = mapped_column()
    message_operation_state: Mapped[str | None] = mapped_column(String(16))
    request_view_ack_id: Mapped[UUID | None] = mapped_column()
    request_initiator_id: Mapped[UUID | None] = mapped_column()
    request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
    operator_audit_id: Mapped[UUID | None] = mapped_column()
    operator_access_version: Mapped[int | None] = mapped_column()
    operator_action: Mapped[str | None] = mapped_column(String(32))
    study_outcome_id: Mapped[UUID | None] = mapped_column()
    study_conversation_id: Mapped[UUID | None] = mapped_column()
    study_outcome_version: Mapped[int | None] = mapped_column()
    study_answer: Mapped[str | None] = mapped_column(String(32))
    peer_feedback_id: Mapped[UUID | None] = mapped_column()
    peer_feedback_version: Mapped[int | None] = mapped_column()
    feedback_again: Mapped[str | None] = mapped_column(String(16))
    study_prompt_id: Mapped[UUID | None] = mapped_column()
    study_prompt_conversation_id: Mapped[UUID | None] = mapped_column()
    notification_preference_version: Mapped[int | None] = mapped_column()
    support_case_id: Mapped[UUID | None] = mapped_column()
    support_case_version: Mapped[int | None] = mapped_column()


Index(
    "ix_product_events_request_time",
    ProductEventRecord.request_id,
    ProductEventRecord.occurred_at,
    ProductEventRecord.id,
    postgresql_where=ProductEventRecord.request_id.is_not(None),
)
Index(
    "ix_product_events_action_time",
    ProductEventRecord.action_id,
    ProductEventRecord.occurred_at,
    ProductEventRecord.id,
    postgresql_where=ProductEventRecord.action_id.is_not(None),
)
Index(
    "ix_product_events_trace_time",
    ProductEventRecord.trace_id,
    ProductEventRecord.occurred_at,
    ProductEventRecord.id,
    postgresql_where=ProductEventRecord.trace_id.is_not(None),
)
