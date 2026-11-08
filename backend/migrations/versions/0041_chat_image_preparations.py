"""Owned chat image preparations; READY remains separate from message delivery."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_chat_image_preparations"
down_revision: str | Sequence[str] | None = "0040_operator_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_image_preparations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("low_id", sa.Uuid(), nullable=False),
        sa.Column("high_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("source_size", sa.Integer(), nullable=False),
        sa.Column("source_digest", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg','image/png')",
            name=op.f("ck_chat_image_preparations_supported_type"),
        ),
        sa.CheckConstraint(
            "account_id IN (low_id,high_id) AND low_id < high_id",
            name=op.f("ck_chat_image_preparations_actual_participant"),
        ),
        sa.CheckConstraint(
            "created_at < upload_expires_at AND upload_expires_at <= processing_expires_at",
            name=op.f("ck_chat_image_preparations_ordered_deadlines"),
        ),
        sa.CheckConstraint(
            "current_version > 0", name=op.f("ck_chat_image_preparations_positive_version")
        ),
        sa.CheckConstraint(
            "octet_length(source_digest)=32", name=op.f("ck_chat_image_preparations_source_digest")
        ),
        sa.CheckConstraint(
            "source_size BETWEEN 1 AND 10000000",
            name=op.f("ck_chat_image_preparations_bounded_source"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_chat_image_preparations_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "low_id", "high_id"],
            ["conversations.id", "conversations.low_id", "conversations.high_id"],
            name=op.f("fk_chat_image_preparations_conversation_id_conversations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_image_preparations")),
        sa.UniqueConstraint(
            "account_id",
            "conversation_id",
            "client_message_id",
            name="uq_chat_images_client_message",
        ),
        sa.UniqueConstraint(
            "id",
            "account_id",
            "conversation_id",
            "client_message_id",
            name="uq_chat_images_owned_message",
        ),
    )
    op.create_index(
        "ix_chat_images_account_created",
        "chat_image_preparations",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_chat_images_conversation_owner",
        "chat_image_preparations",
        ["conversation_id", "account_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "chat_image_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("failure", sa.String(length=32), nullable=True),
        sa.Column("display_width", sa.Integer(), nullable=True),
        sa.Column("display_height", sa.Integer(), nullable=True),
        sa.Column("display_size", sa.Integer(), nullable=True),
        sa.Column("display_digest", sa.LargeBinary(), nullable=True),
        sa.CheckConstraint(
            "(outcome='processing')=(finished_at IS NULL)",
            name=op.f("ck_chat_image_attempts_finish_required"),
        ),
        sa.CheckConstraint(
            "(outcome='retry')=(next_attempt_at IS NOT NULL)",
            name=op.f("ck_chat_image_attempts_retry_required"),
        ),
        sa.CheckConstraint(
            "failure IS NULL OR failure IN "
            "('invalid_image','unsupported_format','too_large','dimensions_exceeded','animated_image','content_changed','account_unavailable','contact_unavailable','storage_unavailable','processing_unavailable')",
            name=op.f("ck_chat_image_attempts_known_failure"),
        ),
        sa.CheckConstraint(
            "outcome IN ('processing','ready','retry','rejected','stale','interrupted')",
            name=op.f("ck_chat_image_attempts_known_outcome"),
        ),
        sa.CheckConstraint(
            "outcome<>'ready' OR display_digest IS NOT NULL",
            name=op.f("ck_chat_image_attempts_ready_metadata"),
        ),
        sa.CheckConstraint(
            "(display_size IS NULL AND display_width IS NULL AND display_height IS NULL "
            "AND display_digest IS NULL) OR (display_size IS NOT NULL AND display_width "
            "IS NOT NULL AND display_height IS NOT NULL AND display_digest IS NOT NULL "
            "AND display_size > 0 AND display_width BETWEEN 1 AND 1024 AND "
            "display_height BETWEEN 1 AND 1024 AND octet_length(display_digest)=32)",
            name=op.f("ck_chat_image_attempts_display_metadata"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_chat_image_attempts_ordered_finish"),
        ),
        sa.CheckConstraint(
            "lease_until > started_at", name=op.f("ck_chat_image_attempts_ordered_lease")
        ),
        sa.CheckConstraint(
            "next_attempt_at IS NULL OR next_attempt_at > finished_at",
            name=op.f("ck_chat_image_attempts_ordered_retry"),
        ),
        sa.CheckConstraint(
            "number BETWEEN 1 AND 3", name=op.f("ck_chat_image_attempts_bounded_number")
        ),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["chat_image_preparations.id"],
            name=op.f("fk_chat_image_attempts_image_id_chat_image_preparations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_image_attempts")),
        sa.UniqueConstraint("image_id", "id", "outcome", name="uq_chat_image_attempt_outcome"),
        sa.UniqueConstraint("image_id", "id", name="uq_chat_image_attempt_source"),
        sa.UniqueConstraint("image_id", "number", name="uq_chat_image_attempt_number"),
    )
    op.create_table(
        "chat_image_revisions",
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("ready_attempt_outcome", sa.String(length=16), nullable=True),
        sa.Column("failure", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "(state='ready' AND ready_attempt_outcome IS NOT NULL AND "
            "ready_attempt_outcome='ready') OR (state<>'ready' AND ready_attempt_outcome"
            " IS NULL)",
            name=op.f("ck_chat_image_revisions_ready_attempt_required"),
        ),
        sa.CheckConstraint(
            "(state='rejected')=(failure IS NOT NULL)",
            name=op.f("ck_chat_image_revisions_failure_required"),
        ),
        sa.CheckConstraint(
            "failure IS NULL OR failure IN "
            "('invalid_image','unsupported_format','too_large','dimensions_exceeded','animated_image','content_changed','account_unavailable','contact_unavailable','storage_unavailable','processing_unavailable')",
            name=op.f("ck_chat_image_revisions_known_failure"),
        ),
        sa.CheckConstraint(
            "state IN ('uploading','queued','processing','ready','rejected','cancelled','expired')",
            name=op.f("ck_chat_image_revisions_known_state"),
        ),
        sa.CheckConstraint(
            "state NOT IN ('processing','ready') OR attempt_id IS NOT NULL",
            name=op.f("ck_chat_image_revisions_attempt_required"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_chat_image_revisions_positive_version")),
        sa.ForeignKeyConstraint(
            ["image_id", "account_id", "conversation_id", "client_message_id"],
            [
                "chat_image_preparations.id",
                "chat_image_preparations.account_id",
                "chat_image_preparations.conversation_id",
                "chat_image_preparations.client_message_id",
            ],
            name=op.f("fk_chat_image_revisions_image_id_chat_image_preparations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["image_id", "attempt_id", "ready_attempt_outcome"],
            [
                "chat_image_attempts.image_id",
                "chat_image_attempts.id",
                "chat_image_attempts.outcome",
            ],
            name="fk_chat_image_actual_ready_attempt",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["image_id", "attempt_id"],
            ["chat_image_attempts.image_id", "chat_image_attempts.id"],
            name="fk_chat_image_revision_attempt",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("image_id", "version", name=op.f("pk_chat_image_revisions")),
        sa.UniqueConstraint(
            "account_id",
            "conversation_id",
            "client_message_id",
            "image_id",
            "version",
            "state",
            name="uq_chat_image_revision_owned_state",
        ),
        sa.UniqueConstraint(
            "account_id",
            "conversation_id",
            "client_message_id",
            "image_id",
            "version",
            name="uq_chat_image_revision_owned_message",
        ),
    )
    op.create_index(
        "ix_chat_image_revisions_state",
        "chat_image_revisions",
        ["state", "updated_at"],
        unique=False,
    )
    op.create_table(
        "chat_image_intents",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND span_id"
            " IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('0',32)"
            " AND span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0',16))",
            name=op.f("ck_chat_image_intents_origin_trace_pair"),
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'", name=op.f("ck_chat_image_intents_intent_key_shape")
        ),
        sa.CheckConstraint(
            "operation IN ('start','finalize','cancel')",
            name=op.f("ck_chat_image_intents_known_operation"),
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND "
            "span_id IS NULL)",
            name=op.f("ck_chat_image_intents_origin_request_context"),
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint)=32", name=op.f("ck_chat_image_intents_fingerprint_length")
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "conversation_id", "client_message_id", "image_id", "result_version"],
            [
                "chat_image_revisions.account_id",
                "chat_image_revisions.conversation_id",
                "chat_image_revisions.client_message_id",
                "chat_image_revisions.image_id",
                "chat_image_revisions.version",
            ],
            name=op.f("fk_chat_image_intents_account_id_chat_image_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_chat_image_intents_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "account_id", "operation", "key", name=op.f("pk_chat_image_intents")
        ),
    )
    op.create_foreign_key(
        "fk_chat_images_current_revision",
        "chat_image_preparations",
        "chat_image_revisions",
        ["id", "current_version"],
        ["image_id", "version"],
        initially="DEFERRED",
        deferrable=True,
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    retained = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM chat_image_preparations) OR "
            "EXISTS(SELECT 1 FROM chat_image_revisions) OR "
            "EXISTS(SELECT 1 FROM chat_image_attempts) OR "
            "EXISTS(SELECT 1 FROM chat_image_intents)"
        )
    )
    if retained:
        raise RuntimeError("Refusing to drop retained chat image preparations")
    op.drop_constraint(
        "fk_chat_images_current_revision", "chat_image_preparations", type_="foreignkey"
    )
    op.drop_table("chat_image_intents")
    op.drop_index("ix_chat_image_revisions_state", table_name="chat_image_revisions")
    op.drop_table("chat_image_revisions")
    op.drop_table("chat_image_attempts")
    op.drop_index("ix_chat_images_conversation_owner", table_name="chat_image_preparations")
    op.drop_index("ix_chat_images_account_created", table_name="chat_image_preparations")
    op.drop_table("chat_image_preparations")
