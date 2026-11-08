"""Owned actual image-report evidence in the existing unified report journal."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_message_image_reports"
down_revision: str | Sequence[str] | None = "0048_chat_image_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_messages_report_image_source",
        "messages",
        [
            "id",
            "conversation_id",
            "author_id",
            "client_message_id",
            "image_id",
            "image_version",
            "image_attempt_id",
            "image_state",
        ],
    )
    op.create_table(
        "message_report_contexts",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("viewer_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("image_version", sa.Integer(), nullable=False),
        sa.Column("image_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("image_state", sa.String(16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(32), nullable=True),
        sa.Column("span_id", sa.String(16), nullable=True),
        sa.UniqueConstraint("id", "viewer_id", name="uq_message_report_context_owner"),
        sa.ForeignKeyConstraint(["viewer_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "message_id",
                "conversation_id",
                "target_id",
                "client_message_id",
                "image_id",
                "image_version",
                "image_attempt_id",
                "image_state",
            ],
            [
                "messages.id",
                "messages.conversation_id",
                "messages.author_id",
                "messages.client_message_id",
                "messages.image_id",
                "messages.image_version",
                "messages.image_attempt_id",
                "messages.image_state",
            ],
            name="fk_message_report_actual_image",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("low_id < high_id", name="canonical_pair"),
        sa.CheckConstraint("viewer_id IN (low_id, high_id)", name="participant_reporter"),
        sa.CheckConstraint(
            "target_id IN (low_id, high_id) AND viewer_id != target_id", name="peer_author"
        ),
        sa.CheckConstraint("image_version > 0 AND image_state='ready'", name="ready_source"),
        sa.CheckConstraint(
            "request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL "
            "AND span_id IS NULL)",
            name="origin_request",
        ),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND "
            "span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != "
            "repeat('0', 32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != "
            "repeat('0', 16))",
            name="origin_trace_pair",
        ),
    )
    op.create_index(
        "ix_message_report_contexts_viewer_issued",
        "message_report_contexts",
        ["viewer_id", "issued_at", "id"],
    )
    op.create_index(
        "ix_message_report_contexts_message_issued",
        "message_report_contexts",
        ["message_id", "issued_at", "id"],
    )
    op.add_column(
        "profile_reports",
        sa.Column("kind", sa.String(16), nullable=False, server_default="profile"),
    )
    op.add_column("profile_reports", sa.Column("message_context_id", sa.Uuid(), nullable=True))
    op.alter_column("profile_reports", "context_id", existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint(
        "evidence_kind",
        "profile_reports",
        "(kind='profile' AND context_id IS NOT NULL AND message_context_id IS"
        " NULL) OR (kind='message_image' AND context_id IS NULL AND "
        "message_context_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_reports_owned_message_context",
        "profile_reports",
        "message_report_contexts",
        ["message_context_id", "reporter_id"],
        ["id", "viewer_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_profile_reports_message_context_submitted",
        "profile_reports",
        ["message_context_id", "submitted_at", "id"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM message_report_contexts) OR "
            "EXISTS(SELECT 1 FROM profile_reports WHERE kind!='profile')"
        )
    ):
        raise RuntimeError("Refusing to drop retained message image report evidence")
    op.drop_index("ix_profile_reports_message_context_submitted", table_name="profile_reports")
    op.drop_constraint("fk_reports_owned_message_context", "profile_reports", type_="foreignkey")
    op.drop_constraint(op.f("ck_profile_reports_evidence_kind"), "profile_reports", type_="check")
    op.alter_column("profile_reports", "context_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("profile_reports", "message_context_id")
    op.drop_column("profile_reports", "kind")
    op.drop_index("ix_message_report_contexts_message_issued", table_name="message_report_contexts")
    op.drop_index("ix_message_report_contexts_viewer_issued", table_name="message_report_contexts")
    op.drop_table("message_report_contexts")
    op.drop_constraint("uq_messages_report_image_source", "messages", type_="unique")
