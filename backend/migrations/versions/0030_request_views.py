"""Retained request disclosures, explicit view acknowledgements and typed receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_request_views"
down_revision: str | Sequence[str] | None = "0029_discovery_topic_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREVIOUS_EVENT_SHAPE = (
    "((((((((kind != 'ai_job.completed' AND ai_job_id IS NULL AND ai_kind IS NULL AND "
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
    "private_passed IS NULL)"
)
EVENT_SHAPE = (
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

OLD_CHECK_0 = (
    "(operation='preview' AND result_kind='preview' AND result_preview_id IS NOT NULL AND "
    "result_request_id IS NULL AND result_conversation_id IS NULL) OR (operation='send' AND "
    "result_kind IN ('sent','outgoing','incoming') AND result_preview_id IS NULL AND "
    "result_request_id IS NOT NULL AND result_request_state IN ('pending','pending_decline') "
    "AND result_conversation_id IS NULL) OR (operation='send' AND result_kind='connected' AND"
    " result_preview_id IS NULL AND result_request_id IS NOT NULL AND "
    "result_request_state='accepted' AND result_conversation_id IS NOT NULL) OR (operation IN"
    " ('decline','undo','withdraw') AND result_kind='request' AND result_preview_id IS NULL "
    "AND result_request_id IS NOT NULL AND result_conversation_id IS NULL AND "
    "((operation='decline' AND result_request_state='pending_decline') OR (operation='undo' "
    "AND result_request_state='pending') OR (operation='withdraw' AND "
    "result_request_state='withdrawn'))) OR (operation='accept' AND result_kind='accepted' "
    "AND result_preview_id IS NULL AND result_request_id IS NOT NULL AND "
    "result_request_state='accepted' AND result_conversation_id IS NOT NULL)"
)
NEW_CHECK_0 = (
    "(((operation='preview' AND result_kind='preview' AND result_preview_id IS NOT NULL AND "
    "result_request_id IS NULL AND result_conversation_id IS NULL) OR ((operation='send' AND "
    "result_kind IN ('sent','outgoing','incoming') OR (operation='preview' AND result_kind IN"
    " ('outgoing','incoming'))) AND result_preview_id IS NULL AND result_request_id IS NOT "
    "NULL AND result_request_state IN ('pending','pending_decline') AND "
    "result_conversation_id IS NULL) OR (operation IN ('preview','send') AND "
    "result_kind='connected' AND result_preview_id IS NULL AND result_request_id IS NOT NULL "
    "AND result_request_state='accepted' AND result_conversation_id IS NOT NULL) OR "
    "(operation IN ('decline','undo','withdraw') AND result_kind='request' AND "
    "result_preview_id IS NULL AND result_request_id IS NOT NULL AND result_conversation_id "
    "IS NULL AND ((operation='decline' AND result_request_state='pending_decline') OR "
    "(operation='undo' AND result_request_state='pending') OR (operation='withdraw' AND "
    "result_request_state='withdrawn'))) OR (operation='accept' AND result_kind='accepted' "
    "AND result_preview_id IS NULL AND result_request_id IS NOT NULL AND "
    "result_request_state='accepted' AND result_conversation_id IS NOT NULL)) AND "
    "result_view_ack_id IS NULL) OR (operation='viewed' AND result_kind='viewed' AND "
    "result_preview_id IS NULL AND result_request_id IS NOT NULL AND result_conversation_id "
    "IS NULL AND result_view_ack_id IS NOT NULL)"
)

OLD_CHECK_1 = "operation IN ('preview','send','decline','undo','withdraw','accept')"
NEW_CHECK_1 = "operation IN ('preview','send','decline','undo','withdraw','accept','viewed')"

OLD_CHECK_2 = (
    "result_kind IN ('preview','sent','outgoing','incoming','connected','request','accepted')"
)
NEW_CHECK_2 = (
    "result_kind IN "
    "('preview','sent','outgoing','incoming','connected','request','accepted','viewed')"
)


def upgrade() -> None:
    op.create_table(
        "request_disclosures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("viewer_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("stored_version", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "stored_version > 0", name=op.f("ck_request_disclosures_positive_stored_version")
        ),
        sa.CheckConstraint(
            "viewer_id IN (sender_id, recipient_id)",
            name=op.f("ck_request_disclosures_participant_viewer"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id", "sender_id", "recipient_id"],
            [
                "connection_requests.id",
                "connection_requests.sender_id",
                "connection_requests.recipient_id",
            ],
            name=op.f("fk_request_disclosures_request_id_connection_requests"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id", "stored_version"],
            ["request_revisions.request_id", "request_revisions.version"],
            name=op.f("fk_request_disclosures_request_id_request_revisions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_disclosures")),
        sa.UniqueConstraint(
            "id",
            "viewer_id",
            "request_id",
            "stored_version",
            name="uq_request_disclosures_owned_source",
        ),
    )
    op.create_index(
        "ix_request_disclosures_viewer_request",
        "request_disclosures",
        ["viewer_id", "request_id"],
        unique=False,
    )
    op.create_table(
        "request_view_acknowledgements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("viewer_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("stored_version", sa.Integer(), nullable=False),
        sa.Column("disclosure_id", sa.Uuid(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "stored_version > 0",
            name=op.f("ck_request_view_acknowledgements_positive_stored_version"),
        ),
        sa.ForeignKeyConstraint(
            ["disclosure_id", "viewer_id", "request_id", "stored_version"],
            [
                "request_disclosures.id",
                "request_disclosures.viewer_id",
                "request_disclosures.request_id",
                "request_disclosures.stored_version",
            ],
            name=op.f("fk_request_view_acknowledgements_disclosure_id_request_disclosures"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_view_acknowledgements")),
        sa.UniqueConstraint(
            "id",
            "viewer_id",
            "request_id",
            "stored_version",
            name="uq_request_view_ack_owned_source",
        ),
        sa.UniqueConstraint("id", "viewer_id", name="uq_request_view_ack_owner"),
        sa.UniqueConstraint(
            "viewer_id", "request_id", "stored_version", name="uq_request_view_ack_source"
        ),
    )
    op.create_index(
        "ix_request_view_ack_viewer_request",
        "request_view_acknowledgements",
        ["viewer_id", "request_id"],
        unique=False,
    )
    op.add_column("product_events", sa.Column("request_view_ack_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_product_events_request_view_owner",
        "product_events",
        "request_view_acknowledgements",
        ["request_view_ack_id", "account_id"],
        ["id", "viewer_id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "request_command_intents", sa.Column("result_view_ack_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_request_command_intents_owned_view_ack",
        "request_command_intents",
        "request_view_acknowledgements",
        ["result_view_ack_id", "actor_id", "result_request_id", "result_request_version"],
        ["id", "viewer_id", "request_id", "stored_version"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("ck_request_command_intents_typed_operation_result"),
        "request_command_intents",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_request_command_intents_typed_operation_result"),
        "request_command_intents",
        NEW_CHECK_0,
    )
    op.drop_constraint(
        op.f("ck_request_command_intents_operation_kind"), "request_command_intents", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_request_command_intents_operation_kind"), "request_command_intents", NEW_CHECK_1
    )
    op.drop_constraint(
        op.f("ck_request_command_intents_result_kind"), "request_command_intents", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_request_command_intents_result_kind"), "request_command_intents", NEW_CHECK_2
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
                "SELECT EXISTS (SELECT 1 FROM request_disclosures) OR "
                "EXISTS (SELECT 1 FROM request_view_acknowledgements) OR "
                "EXISTS (SELECT 1 FROM request_command_intents WHERE operation='viewed' OR "
                "(operation='preview' AND result_kind <> 'preview'))"
            )
        )
        .scalar_one()
    )
    if retained:
        raise RuntimeError("Cannot remove retained request disclosure and viewed history")
    op.drop_constraint(
        op.f("ck_request_command_intents_typed_operation_result"),
        "request_command_intents",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_request_command_intents_typed_operation_result"),
        "request_command_intents",
        OLD_CHECK_0,
    )
    op.drop_constraint(
        op.f("ck_request_command_intents_operation_kind"), "request_command_intents", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_request_command_intents_operation_kind"), "request_command_intents", OLD_CHECK_1
    )
    op.drop_constraint(
        op.f("ck_request_command_intents_result_kind"), "request_command_intents", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_request_command_intents_result_kind"), "request_command_intents", OLD_CHECK_2
    )
    op.drop_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_product_events_event_reference_shape"), "product_events", PREVIOUS_EVENT_SHAPE
    )
    op.drop_constraint(
        "fk_request_command_intents_owned_view_ack", "request_command_intents", type_="foreignkey"
    )
    op.drop_column("request_command_intents", "result_view_ack_id")
    op.drop_constraint("fk_product_events_request_view_owner", "product_events", type_="foreignkey")
    op.drop_column("product_events", "request_view_ack_id")
    op.drop_index("ix_request_view_ack_viewer_request", table_name="request_view_acknowledgements")
    op.drop_table("request_view_acknowledgements")
    op.drop_index("ix_request_disclosures_viewer_request", table_name="request_disclosures")
    op.drop_table("request_disclosures")
