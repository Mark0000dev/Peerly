"""Explicit retained operator grants, audited reads and canonical source correlation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_operator_inspection"
down_revision: str | Sequence[str] | None = "0033_conversation_goal_shares"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
PREVIOUS_EVENT_SHAPE = (
    "((((((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL AND"
    " ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved', 'goal.completed') "
    "AND goal_id IS NOT NULL AND goal_version IS NOT NULL AND topic_present IS NOT NULL AND "
    "shared_learning IS NOT NULL AND profile_version IS NULL AND visibility_version IS NULL "
    "AND onboarding_task IS NULL) OR (kind = 'profile.ready' AND profile_version IS NOT NULL "
    "AND onboarding_task IS NOT NULL AND onboarding_task IN ('find_help', 'offer_help') AND "
    "goal_id IS NULL AND goal_version IS NULL AND visibility_version IS NULL AND subject_id "
    "IS NULL AND topic_present IS NULL AND shared_learning IS NULL) OR (kind IN "
    "('profile.hidden', 'profile.restored', 'discovery.exposure_confirmed') AND "
    "visibility_version IS NOT NULL AND goal_id IS NULL AND goal_version IS NULL AND "
    "profile_version IS NULL AND onboarding_task IS NULL AND subject_id IS NULL AND "
    "topic_present IS NULL AND shared_learning IS NULL) OR (kind = 'auth.email_confirmed' AND"
    " goal_id IS NULL AND goal_version IS NULL AND profile_version IS NULL AND "
    "visibility_version IS NULL AND onboarding_task IS NULL AND subject_id IS NULL AND "
    "topic_present IS NULL AND shared_learning IS NULL))) OR (kind = 'ai_job.completed' AND "
    "ai_job_id IS NOT NULL AND ai_kind IS NOT NULL AND ai_kind IN "
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
    "request_initiator_id IS NULL)"
)
EVENT_SHAPE = (
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


def upgrade() -> None:
    op.create_table(
        "operator_access",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "current_version > 0", name=op.f("ck_operator_access_positive_revision")
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "current_version"],
            ["operator_access_revisions.account_id", "operator_access_revisions.version"],
            name="fk_operator_access_current_revision",
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_operator_access_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["external_identities.account_id"],
            name="fk_operator_access_google_link",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("pk_operator_access")),
    )
    op.create_table(
        "operator_access_revisions",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by_id", sa.Uuid(), nullable=True),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND "
            "span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != "
            "repeat('0', 32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', "
            "16))",
            name=op.f("ck_operator_access_revisions_origin_trace_pair"),
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND"
            " span_id IS NULL)",
            name=op.f("ck_operator_access_revisions_origin_request_context"),
        ),
        sa.CheckConstraint(
            "version > 0", name=op.f("ck_operator_access_revisions_positive_revision")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["operator_access.account_id"],
            name=op.f("fk_operator_access_revisions_account_id_operator_access"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_id"],
            ["accounts.id"],
            name=op.f("fk_operator_access_revisions_changed_by_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("account_id", "version", name=op.f("pk_operator_access_revisions")),
        sa.UniqueConstraint(
            "account_id", "version", "active", name="uq_operator_access_revisions_state"
        ),
    )
    op.create_table(
        "operator_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("operator_access_version", sa.Integer(), nullable=False),
        sa.Column("operator_access_active", sa.Boolean(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("resource_kind", sa.String(length=16), nullable=False),
        sa.Column("requested_id", sa.Uuid(), nullable=True),
        sa.Column("result_ids", sa.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("query_fingerprint", sa.LargeBinary(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(action='search_accounts' AND resource_kind='account' AND requested_id IS "
            "NULL AND outcome='search' AND query_fingerprint IS NOT NULL AND "
            "octet_length(query_fingerprint)=32 AND cardinality(result_ids)<=20) OR "
            "(action='read_account' AND resource_kind='account' AND requested_id IS NOT"
            " NULL AND query_fingerprint IS NULL AND ((outcome='read' AND "
            "result_ids=ARRAY[requested_id]) OR (outcome='not_found' AND "
            "cardinality(result_ids)=0))) OR (action='read_conversation_messages' AND "
            "resource_kind='conversation' AND requested_id IS NOT NULL AND "
            "query_fingerprint IS NULL AND ((outcome='read' AND "
            "cardinality(result_ids)<=50) OR (outcome='not_found' AND "
            "cardinality(result_ids)=0)))",
            name=op.f("ck_operator_audits_fixed_inspection_shape"),
        ),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND "
            "span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != "
            "repeat('0', 32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', "
            "16))",
            name=op.f("ck_operator_audits_origin_trace_pair"),
        ),
        sa.CheckConstraint(
            "cardinality(result_ids) BETWEEN 0 AND 50 AND array_position(result_ids, NULL) IS NULL",
            name=op.f("ck_operator_audits_bounded_result_ids"),
        ),
        sa.CheckConstraint(
            "cardinality(result_ids)=0 OR array_ndims(result_ids)=1",
            name=op.f("ck_operator_audits_one_dimensional_result_ids"),
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND"
            " span_id IS NULL)",
            name=op.f("ck_operator_audits_origin_request_context"),
        ),
        sa.CheckConstraint(
            "operator_access_active IS TRUE", name=op.f("ck_operator_audits_active_grant_source")
        ),
        sa.ForeignKeyConstraint(
            ["operator_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            name="fk_operator_audits_actual_active_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["accounts.id"],
            name=op.f("fk_operator_audits_operator_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operator_audits")),
        sa.UniqueConstraint(
            "id",
            "operator_id",
            "operator_access_version",
            "action",
            name="uq_operator_audits_source",
        ),
    )
    op.create_index(
        "ix_operator_audits_actor_time",
        "operator_audits",
        ["operator_id", "occurred_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_operator_audits_resource_time",
        "operator_audits",
        ["resource_kind", "requested_id", "occurred_at", "id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_operator_access_current_revision",
        "operator_access",
        "operator_access_revisions",
        ["account_id", "current_version"],
        ["account_id", "version"],
        ondelete="RESTRICT",
        initially="DEFERRED",
        deferrable=True,
    )
    op.add_column("product_events", sa.Column("operator_audit_id", sa.Uuid(), nullable=True))
    op.add_column(
        "product_events", sa.Column("operator_access_version", sa.Integer(), nullable=True)
    )
    op.add_column(
        "product_events", sa.Column("operator_action", sa.String(length=32), nullable=True)
    )
    op.create_foreign_key(
        "fk_product_events_operator_audit_source",
        "product_events",
        "operator_audits",
        ["operator_audit_id", "account_id", "operator_access_version", "operator_action"],
        ["id", "operator_id", "operator_access_version", "action"],
        ondelete="RESTRICT",
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
                "SELECT EXISTS (SELECT 1 FROM operator_access) OR EXISTS (SELECT 1 FROM "
                "operator_audits)"
            )
        )
        .scalar_one()
    )
    if retained:
        raise RuntimeError("Cannot remove retained operator grants or inspection audit history")
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", PREVIOUS_EVENT_SHAPE
    )
    op.drop_constraint(
        "fk_product_events_operator_audit_source", "product_events", type_="foreignkey"
    )
    op.drop_column("product_events", "operator_action")
    op.drop_column("product_events", "operator_access_version")
    op.drop_column("product_events", "operator_audit_id")
    op.drop_index("ix_operator_audits_resource_time", table_name="operator_audits")
    op.drop_index("ix_operator_audits_actor_time", table_name="operator_audits")
    op.drop_constraint("fk_operator_access_current_revision", "operator_access", type_="foreignkey")
    op.drop_table("operator_audits")
    op.drop_table("operator_access_revisions")
    op.drop_table("operator_access")
