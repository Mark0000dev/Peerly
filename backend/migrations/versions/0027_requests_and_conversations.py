"""Retained immutable requests and actual unique accepted conversations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_requests_and_conversations"
down_revision: str | Sequence[str] | None = "0026_discovery_pass_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "request_previews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_json", sa.Text(), nullable=False),
        sa.Column("sender_goal_id", sa.Uuid(), nullable=True),
        sa.Column("sender_goal_version", sa.Integer(), nullable=True),
        sa.Column("recipient_goal_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_goal_version", sa.Integer(), nullable=True),
        sa.Column("sender_help_version", sa.Integer(), nullable=True),
        sa.Column("recipient_help_version", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(mode='find_help' AND sender_goal_id IS NOT NULL AND recipient_goal_id I"
            "S NULL AND sender_help_version IS NULL AND recipient_help_version IS NOT"
            " NULL) OR (mode='offer_help' AND sender_goal_id IS NULL AND recipient_go"
            "al_id IS NOT NULL AND sender_help_version IS NOT NULL AND recipient_help"
            "_version IS NULL) OR (mode='study_together' AND sender_goal_id IS NOT NU"
            "LL AND recipient_goal_id IS NOT NULL AND sender_help_version IS NULL AND"
            " recipient_help_version IS NULL)",
            name=op.f("ck_request_previews_mode_sources"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_json::jsonb) = 'object'",
            name=op.f("ck_request_previews_source_object"),
        ),
        sa.CheckConstraint(
            "mode IN ('find_help','offer_help','study_together')",
            name=op.f("ck_request_previews_request_mode"),
        ),
        sa.CheckConstraint(
            "(sender_goal_id IS NULL) = (sender_goal_version IS NULL) AND (recipient_"
            "goal_id IS NULL) = (recipient_goal_version IS NULL)",
            name=op.f("ck_request_previews_complete_goal_refs"),
        ),
        sa.CheckConstraint(
            "(sender_goal_version IS NULL OR sender_goal_version > 0) AND (recipient_"
            "goal_version IS NULL OR recipient_goal_version > 0) AND (sender_help_ver"
            "sion IS NULL OR sender_help_version > 0) AND (recipient_help_version IS "
            "NULL OR recipient_help_version > 0)",
            name=op.f("ck_request_previews_positive_source_versions"),
        ),
        sa.CheckConstraint(
            "octet_length(source_json) BETWEEN 1 AND 32768",
            name=op.f("ck_request_previews_bounded_source"),
        ),
        sa.CheckConstraint(
            "sender_id <> recipient_id", name=op.f("ck_request_previews_distinct_participants")
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id", "recipient_goal_id", "recipient_goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            name=op.f("fk_request_previews_recipient_id_goal_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id", "recipient_help_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            name=op.f("fk_request_previews_recipient_id_help_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["accounts.id"],
            name=op.f("fk_request_previews_recipient_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id", "sender_goal_id", "sender_goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            name=op.f("fk_request_previews_sender_id_goal_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id", "sender_help_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            name=op.f("fk_request_previews_sender_id_help_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["accounts.id"],
            name=op.f("fk_request_previews_sender_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_request_previews_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_previews")),
        sa.UniqueConstraint(
            "id", "sender_id", "recipient_id", name="uq_request_previews_participants"
        ),
    )
    op.create_table(
        "connection_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("relationship_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("preview_id", sa.Uuid(), nullable=False),
        sa.Column("request_text", sa.String(length=240), nullable=False),
        sa.Column("note", sa.String(length=240), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("decision_sequence", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "state IN ('pending','pending_decline','declined','withdrawn','expired','"
            "unavailable','accepted')",
            name=op.f("ck_connection_requests_request_state"),
        ),
        sa.CheckConstraint(
            "(sender_id=low_id AND recipient_id=high_id) OR (sender_id=high_id AND re"
            "cipient_id=low_id)",
            name=op.f("ck_connection_requests_directional_participants"),
        ),
        sa.CheckConstraint(
            "current_version > 0 AND decision_sequence > 0",
            name=op.f("ck_connection_requests_positive_versions"),
        ),
        sa.CheckConstraint(
            "expires_at > sent_at", name=op.f("ck_connection_requests_valid_expiry")
        ),
        sa.CheckConstraint(
            "length(request_text) BETWEEN 1 AND 240",
            name=op.f("ck_connection_requests_request_text_length"),
        ),
        sa.CheckConstraint("low_id < high_id", name=op.f("ck_connection_requests_canonical_pair")),
        sa.CheckConstraint(
            "note IS NULL OR length(note) BETWEEN 1 AND 240",
            name=op.f("ck_connection_requests_note_length"),
        ),
        sa.ForeignKeyConstraint(
            ["preview_id", "sender_id", "recipient_id"],
            ["request_previews.id", "request_previews.sender_id", "request_previews.recipient_id"],
            name=op.f("fk_connection_requests_preview_id_request_previews"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["relationship_id", "low_id", "high_id"],
            ["relationships.id", "relationships.low_id", "relationships.high_id"],
            name=op.f("fk_connection_requests_relationship_id_relationships"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_connection_requests")),
        sa.UniqueConstraint("id", "relationship_id", name="uq_connection_requests_relationship"),
        sa.UniqueConstraint(
            "id", "sender_id", "recipient_id", name="uq_connection_requests_participants"
        ),
        sa.UniqueConstraint(
            "sender_id", "decision_sequence", name="uq_connection_requests_decision"
        ),
    )
    op.create_index(
        "ix_connection_requests_pending_expiry",
        "connection_requests",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("state IN ('pending','pending_decline')"),
    )
    op.create_index(
        "ix_connection_requests_recipient_state",
        "connection_requests",
        ["recipient_id", "state", "sent_at"],
        unique=False,
    )
    op.create_index(
        "ix_connection_requests_sender_state",
        "connection_requests",
        ["sender_id", "state", "sent_at"],
        unique=False,
    )
    op.create_index(
        "uq_connection_requests_pending_pair",
        "connection_requests",
        ["relationship_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('pending','pending_decline')"),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("relationship_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_request_version", sa.Integer(), nullable=False),
        sa.Column("request_state", sa.String(length=20), nullable=False),
        sa.Column("next_message_sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "request_state = 'accepted'", name=op.f("ck_conversations_accepted_state")
        ),
        sa.CheckConstraint(
            "accepted_request_version > 1", name=op.f("ck_conversations_accepted_revision")
        ),
        sa.CheckConstraint("low_id < high_id", name=op.f("ck_conversations_canonical_pair")),
        sa.CheckConstraint(
            "next_message_sequence > 0", name=op.f("ck_conversations_positive_message_sequence")
        ),
        sa.ForeignKeyConstraint(
            ["relationship_id", "low_id", "high_id"],
            ["relationships.id", "relationships.low_id", "relationships.high_id"],
            name=op.f("fk_conversations_relationship_id_relationships"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["request_id", "relationship_id"],
            ["connection_requests.id", "connection_requests.relationship_id"],
            name="fk_conversations_request_relationship",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint("id", "request_id", name="uq_conversations_source_request"),
        sa.UniqueConstraint("relationship_id", name="uq_conversations_relationship"),
    )
    op.create_table(
        "request_revisions",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decline_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(state = 'accepted') = (conversation_id IS NOT NULL)",
            name=op.f("ck_request_revisions_actual_accepted_conversation"),
        ),
        sa.CheckConstraint(
            "(state = 'pending_decline') = (decline_until IS NOT NULL)",
            name=op.f("ck_request_revisions_decline_deadline_state"),
        ),
        sa.CheckConstraint(
            "decline_until IS NULL OR decline_until = changed_at + interval '10 seconds'",
            name=op.f("ck_request_revisions_fixed_undo_window"),
        ),
        sa.CheckConstraint(
            "state IN ('pending','pending_decline','declined','withdrawn','expired','"
            "unavailable','accepted')",
            name=op.f("ck_request_revisions_request_state"),
        ),
        sa.CheckConstraint(
            "version <> 1 OR state = 'pending'", name=op.f("ck_request_revisions_initial_pending")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_request_revisions_positive_version")),
        sa.ForeignKeyConstraint(
            ["conversation_id", "request_id"],
            ["conversations.id", "conversations.request_id"],
            name="fk_request_revisions_conversation",
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["connection_requests.id"],
            name=op.f("fk_request_revisions_request_id_connection_requests"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("request_id", "version", name=op.f("pk_request_revisions")),
        sa.UniqueConstraint("request_id", "version", "state", name="uq_request_revisions_state"),
    )
    op.create_index(
        "ix_request_revisions_due_decline",
        "request_revisions",
        ["decline_until"],
        unique=False,
        postgresql_where=sa.text("state = 'pending_decline'"),
    )
    op.create_table(
        "request_send_days",
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("local_day", sa.Date(), nullable=False),
        sa.Column("successful_count", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "successful_count > 0", name=op.f("ck_request_send_days_positive_count")
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["accounts.id"],
            name=op.f("fk_request_send_days_sender_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("sender_id", "local_day", name=op.f("pk_request_send_days")),
    )
    op.create_table(
        "request_command_intents",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("peer_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_kind", sa.String(length=16), nullable=False),
        sa.Column("result_preview_id", sa.Uuid(), nullable=True),
        sa.Column("result_request_id", sa.Uuid(), nullable=True),
        sa.Column("result_request_version", sa.Integer(), nullable=True),
        sa.Column("result_request_state", sa.String(length=24), nullable=True),
        sa.Column("result_sender_id", sa.Uuid(), nullable=True),
        sa.Column("result_recipient_id", sa.Uuid(), nullable=True),
        sa.Column("result_conversation_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(operation='preview' AND result_kind='preview' AND result_preview_id IS "
            "NOT NULL AND result_request_id IS NULL AND result_conversation_id IS NUL"
            "L) OR (operation='send' AND result_kind IN ('sent','outgoing','incoming'"
            ") AND result_preview_id IS NULL AND result_request_id IS NOT NULL AND re"
            "sult_request_state IN ('pending','pending_decline') AND result_conversat"
            "ion_id IS NULL) OR (operation='send' AND result_kind='connected' AND res"
            "ult_preview_id IS NULL AND result_request_id IS NOT NULL AND result_requ"
            "est_state='accepted' AND result_conversation_id IS NOT NULL) OR (operati"
            "on IN ('decline','undo','withdraw') AND result_kind='request' AND result"
            "_preview_id IS NULL AND result_request_id IS NOT NULL AND result_convers"
            "ation_id IS NULL AND ((operation='decline' AND result_request_state='pen"
            "ding_decline') OR (operation='undo' AND result_request_state='pending') "
            "OR (operation='withdraw' AND result_request_state='withdrawn'))) OR (ope"
            "ration='accept' AND result_kind='accepted' AND result_preview_id IS NULL"
            " AND result_request_id IS NOT NULL AND result_request_state='accepted' A"
            "ND result_conversation_id IS NOT NULL)",
            name=op.f("ck_request_command_intents_typed_operation_result"),
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'",
            name=op.f("ck_request_command_intents_intent_key_shape"),
        ),
        sa.CheckConstraint(
            "operation <> 'withdraw' OR (actor_id=result_sender_id AND peer_id=result"
            "_recipient_id)",
            name=op.f("ck_request_command_intents_sender_withdrawal"),
        ),
        sa.CheckConstraint(
            "operation IN ('preview','send','decline','undo','withdraw','accept')",
            name=op.f("ck_request_command_intents_operation_kind"),
        ),
        sa.CheckConstraint(
            "operation NOT IN ('decline','undo','accept') OR (actor_id=result_recipie"
            "nt_id AND peer_id=result_sender_id)",
            name=op.f("ck_request_command_intents_recipient_operation"),
        ),
        sa.CheckConstraint(
            "result_kind <> 'incoming' OR (actor_id=result_recipient_id AND peer_id=r"
            "esult_sender_id)",
            name=op.f("ck_request_command_intents_incoming_result_direction"),
        ),
        sa.CheckConstraint(
            "result_kind IN ('preview','sent','outgoing','incoming','connected','requ"
            "est','accepted')",
            name=op.f("ck_request_command_intents_result_kind"),
        ),
        sa.CheckConstraint(
            "result_kind NOT IN ('sent','outgoing') OR (actor_id=result_sender_id AND"
            " peer_id=result_recipient_id)",
            name=op.f("ck_request_command_intents_outgoing_result_direction"),
        ),
        sa.CheckConstraint(
            "(result_request_id IS NULL) = (result_request_version IS NULL) AND (resu"
            "lt_request_id IS NULL) = (result_request_state IS NULL) AND (result_requ"
            "est_id IS NULL) = (result_sender_id IS NULL) AND (result_request_id IS N"
            "ULL) = (result_recipient_id IS NULL)",
            name=op.f("ck_request_command_intents_complete_request_result"),
        ),
        sa.CheckConstraint(
            "actor_id <> peer_id", name=op.f("ck_request_command_intents_distinct_participants")
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32",
            name=op.f("ck_request_command_intents_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "result_request_id IS NULL OR ((actor_id=result_sender_id AND peer_id=res"
            "ult_recipient_id) OR (actor_id=result_recipient_id AND peer_id=result_se"
            "nder_id))",
            name=op.f("ck_request_command_intents_owned_result_pair"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_request_command_intents_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["peer_id"],
            ["accounts.id"],
            name=op.f("fk_request_command_intents_peer_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_conversation_id", "result_request_id"],
            ["conversations.id", "conversations.request_id"],
            name=op.f("fk_request_command_intents_result_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_preview_id", "actor_id", "peer_id"],
            ["request_previews.id", "request_previews.sender_id", "request_previews.recipient_id"],
            name=op.f("fk_request_command_intents_result_preview_id_request_previews"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_request_id", "result_request_version", "result_request_state"],
            [
                "request_revisions.request_id",
                "request_revisions.version",
                "request_revisions.state",
            ],
            name=op.f("fk_request_command_intents_result_request_id_request_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_request_id", "result_sender_id", "result_recipient_id"],
            [
                "connection_requests.id",
                "connection_requests.sender_id",
                "connection_requests.recipient_id",
            ],
            name=op.f("fk_request_command_intents_result_request_id_connection_requests"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "actor_id", "operation", "key", name=op.f("pk_request_command_intents")
        ),
    )
    op.create_foreign_key(
        "fk_connection_requests_current_revision",
        "connection_requests",
        "request_revisions",
        ["id", "current_version", "state"],
        ["request_id", "version", "state"],
        ondelete="RESTRICT",
        initially="DEFERRED",
        deferrable=True,
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_conversations_actual_acceptance",
        "conversations",
        "request_revisions",
        ["request_id", "accepted_request_version", "request_state"],
        ["request_id", "version", "state"],
        ondelete="RESTRICT",
        initially="DEFERRED",
        deferrable=True,
        use_alter=True,
    )


def downgrade() -> None:
    retained = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM request_previews) OR "
                "EXISTS (SELECT 1 FROM connection_requests) OR "
                "EXISTS (SELECT 1 FROM conversations) OR "
                "EXISTS (SELECT 1 FROM request_send_days)"
            )
        )
        .scalar_one()
    )
    if retained:
        raise RuntimeError("Cannot remove retained request and conversation history")
    op.drop_constraint(
        "fk_connection_requests_current_revision", "connection_requests", type_="foreignkey"
    )
    op.drop_constraint("fk_conversations_actual_acceptance", "conversations", type_="foreignkey")
    op.drop_table("request_command_intents")
    op.drop_table("request_send_days")
    op.drop_table("request_revisions")
    op.drop_table("conversations")
    op.drop_table("connection_requests")
    op.drop_table("request_previews")
