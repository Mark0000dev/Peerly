"""Terminal message operations, immutable text messages and retained canonical outcomes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_text_messages"
down_revision: str | Sequence[str] | None = "0030_request_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
PREVIOUS_EVENT_SHAPE = (
    "((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL AND "
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
    "connection_request_recipient_id IS NULL AND request_initiator_id IS NULL)"
)
EVENT_SHAPE = (
    "((((((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL AND "
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
    "request_initiator_id IS NULL)"
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_conversations_participants", "conversations", ["id", "low_id", "high_id"]
    )
    op.create_table(
        "message_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(state='confirmed' AND message_id IS NOT NULL AND cancelled_at IS NULL) OR "
            "(state='cancelled' AND message_id IS NULL AND cancelled_at IS NOT NULL)",
            name=op.f("ck_message_operations_terminal_outcome_shape"),
        ),
        sa.CheckConstraint(
            "author_id IN (low_id, high_id)", name=op.f("ck_message_operations_participant_author")
        ),
        sa.CheckConstraint("low_id < high_id", name=op.f("ck_message_operations_canonical_pair")),
        sa.ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            name=op.f("fk_message_operations_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["message_id", "id"],
            ["messages.id", "messages.operation_id"],
            name="fk_message_operations_actual_message",
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
            use_alter=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_operations")),
        sa.UniqueConstraint(
            "conversation_id",
            "author_id",
            "client_message_id",
            name="uq_message_operations_logical_send",
        ),
        sa.UniqueConstraint(
            "id", "author_id", "conversation_id", name="uq_message_operations_owned_scope"
        ),
        sa.UniqueConstraint("id", "author_id", "state", name="uq_message_operations_owned_state"),
        sa.UniqueConstraint(
            "id",
            "conversation_id",
            "low_id",
            "high_id",
            "author_id",
            "client_message_id",
            "state",
            name="uq_message_operations_owned_outcome",
        ),
    )
    op.create_table(
        "message_command_intents",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("result_operation_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'",
            name=op.f("ck_message_command_intents_intent_key_shape"),
        ),
        sa.CheckConstraint(
            "operation IN ('send','cancel')", name=op.f("ck_message_command_intents_operation_kind")
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint)=32",
            name=op.f("ck_message_command_intents_fingerprint_length"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_message_command_intents_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_operation_id", "actor_id", "conversation_id"],
            [
                "message_operations.id",
                "message_operations.author_id",
                "message_operations.conversation_id",
            ],
            name=op.f("fk_message_command_intents_result_operation_id_message_operations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "actor_id", "operation", "key", name=op.f("pk_message_command_intents")
        ),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(text) BETWEEN 1 AND 2000 AND text ~ '[^[:space:]]'",
            name=op.f("ck_messages_nonblank_bounded_text"),
        ),
        sa.CheckConstraint("state='confirmed'", name=op.f("ck_messages_confirmed_state")),
        sa.CheckConstraint("sequence > 0", name=op.f("ck_messages_positive_sequence")),
        sa.ForeignKeyConstraint(
            [
                "operation_id",
                "conversation_id",
                "low_id",
                "high_id",
                "author_id",
                "client_message_id",
                "state",
            ],
            [
                "message_operations.id",
                "message_operations.conversation_id",
                "message_operations.low_id",
                "message_operations.high_id",
                "message_operations.author_id",
                "message_operations.client_message_id",
                "message_operations.state",
            ],
            name=op.f("fk_messages_operation_id_message_operations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_messages_conversation_sequence"
        ),
        sa.UniqueConstraint("id", "operation_id", name="uq_messages_terminal_root"),
        sa.UniqueConstraint("operation_id", name="uq_messages_operation"),
    )
    op.alter_column(
        "conversations",
        "next_message_sequence",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.add_column("product_events", sa.Column("message_operation_id", sa.Uuid(), nullable=True))
    op.add_column(
        "product_events", sa.Column("message_operation_state", sa.String(length=16), nullable=True)
    )
    op.create_foreign_key(
        "fk_product_events_message_outcome",
        "product_events",
        "message_operations",
        ["message_operation_id", "account_id", "message_operation_state"],
        ["id", "author_id", "state"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_message_operations_actual_message",
        "message_operations",
        "messages",
        ["message_id", "id"],
        ["id", "operation_id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
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
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM message_operations)"))
        .scalar_one()
    )
    if retained:
        raise RuntimeError("Cannot remove retained message and cancellation history")
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", PREVIOUS_EVENT_SHAPE
    )
    op.drop_constraint(
        "fk_message_operations_actual_message", "message_operations", type_="foreignkey"
    )
    op.drop_constraint("fk_product_events_message_outcome", "product_events", type_="foreignkey")
    op.drop_column("product_events", "message_operation_state")
    op.drop_column("product_events", "message_operation_id")
    op.alter_column(
        "conversations",
        "next_message_sequence",
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        existing_nullable=False,
    )
    op.drop_table("messages")
    op.drop_table("message_command_intents")
    op.drop_table("message_operations")
    op.drop_constraint("uq_conversations_participants", "conversations", type_="unique")
