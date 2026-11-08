"""Explicit immutable conversation goal shares and source-bound canonical outcomes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_conversation_goal_shares"
down_revision: str | Sequence[str] | None = "0032_conversation_reads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
PREVIOUS_EVENT_SHAPE = (
    "((((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL AND "
    "ai_state IS NULL AND ai_reason IS NULL) AND ((kind IN ('goal.saved', 'goal.completed') "
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
    "request_view_ack_id IS NULL AND request_initiator_id IS NULL)"
)
EVENT_SHAPE = (
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


def upgrade() -> None:
    op.create_table(
        "conversation_goal_shares",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("goal_version", sa.Integer(), nullable=False),
        sa.Column("context_version", sa.BigInteger(), nullable=False),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "goal_version > 0 AND context_version > 0",
            name=op.f("ck_conversation_goal_shares_positive_source_versions"),
        ),
        sa.CheckConstraint(
            "low_id < high_id", name=op.f("ck_conversation_goal_shares_canonical_pair")
        ),
        sa.CheckConstraint(
            "owner_id IN (low_id, high_id)",
            name=op.f("ck_conversation_goal_shares_participant_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            name=op.f("fk_conversation_goal_shares_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "goal_id", "goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            name=op.f("fk_conversation_goal_shares_owner_id_goal_revisions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_goal_shares")),
        sa.UniqueConstraint(
            "conversation_id", "context_version", name="uq_conversation_goal_shares_version"
        ),
        sa.UniqueConstraint(
            "id",
            "owner_id",
            "conversation_id",
            "context_version",
            name="uq_conversation_goal_shares_source",
        ),
        sa.UniqueConstraint(
            "id", "owner_id", "conversation_id", name="uq_conversation_goal_shares_owner"
        ),
    )
    op.create_table(
        "conversation_goal_share_heads",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("context_version", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "context_version > 0",
            name=op.f("ck_conversation_goal_share_heads_actual_shared_context"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "context_version"],
            [
                "conversation_goal_shares.conversation_id",
                "conversation_goal_shares.context_version",
            ],
            name=op.f("fk_conversation_goal_share_heads_conversation_id_conversation_goal_shares"),
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_conversation_goal_share_heads_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("conversation_id", name=op.f("pk_conversation_goal_share_heads")),
    )
    op.create_table(
        "conversation_goal_share_intents",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("result_share_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'",
            name=op.f("ck_conversation_goal_share_intents_intent_key_shape"),
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32",
            name=op.f("ck_conversation_goal_share_intents_fingerprint_length"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_conversation_goal_share_intents_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_conversation_goal_share_intents_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_share_id", "actor_id", "conversation_id"],
            [
                "conversation_goal_shares.id",
                "conversation_goal_shares.owner_id",
                "conversation_goal_shares.conversation_id",
            ],
            name=op.f(
                "fk_conversation_goal_share_intents_result_share_id_conversation_goal_shares"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("actor_id", "key", name=op.f("pk_conversation_goal_share_intents")),
    )
    op.add_column("product_events", sa.Column("goal_share_id", sa.Uuid(), nullable=True))
    op.add_column(
        "product_events", sa.Column("goal_share_context_version", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "product_events", sa.Column("goal_share_conversation_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_product_events_goal_share_source",
        "product_events",
        "conversation_goal_shares",
        ["goal_share_id", "account_id", "goal_share_conversation_id", "goal_share_context_version"],
        ["id", "owner_id", "conversation_id", "context_version"],
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
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM conversation_goal_shares)"))
        .scalar_one()
    )
    if retained:
        raise RuntimeError("Cannot remove retained shared goal context history")
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", PREVIOUS_EVENT_SHAPE
    )
    op.drop_constraint("fk_product_events_goal_share_source", "product_events", type_="foreignkey")
    op.drop_column("product_events", "goal_share_conversation_id")
    op.drop_column("product_events", "goal_share_context_version")
    op.drop_column("product_events", "goal_share_id")
    op.drop_table("conversation_goal_share_intents")
    op.drop_table("conversation_goal_share_heads")
    op.drop_table("conversation_goal_shares")
