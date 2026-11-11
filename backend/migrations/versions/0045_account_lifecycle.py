"""Retained lifecycle sources, exact command receipts and owned deletion workflows."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_account_lifecycle"
down_revision: str | Sequence[str] | None = "0044_chat_image_queue_origins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_deletion_workflows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_secret_digest", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint(
            "expires_at>created_at", name=op.f("ck_account_deletion_workflows_valid_lifetime")
        ),
        sa.CheckConstraint(
            "generation>0", name=op.f("ck_account_deletion_workflows_positive_generation")
        ),
        sa.CheckConstraint(
            "octet_length(status_secret_digest)=32",
            name=op.f("ck_account_deletion_workflows_status_digest_length"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_account_deletion_workflows_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "account_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_deletion_workflow_actual_session",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_deletion_workflows")),
        sa.UniqueConstraint(
            "id", "account_id", "session_id", name="uq_deletion_workflow_owned_session"
        ),
        sa.UniqueConstraint(
            "session_id", "generation", name="uq_deletion_workflow_session_generation"
        ),
        sa.UniqueConstraint("status_secret_digest", name="uq_deletion_workflow_status_digest"),
    )
    op.create_table(
        "account_lifecycle_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(length=6), nullable=False),
        sa.Column("before_banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("before_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("after_banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("after_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("actor_session_id", sa.Uuid(), nullable=False),
        sa.Column("operator_access_version", sa.Integer(), nullable=True),
        sa.Column("operator_access_active", sa.Boolean(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "((operation='ban' AND before_banned_at IS NULL AND after_banned_at IS NO"
            "T NULL AND after_banned_at=changed_at AND after_deleted_at IS NOT DISTIN"
            "CT FROM before_deleted_at) OR (operation='unban' AND before_banned_at IS"
            " NOT NULL AND after_banned_at IS NULL AND after_deleted_at IS NOT DISTIN"
            "CT FROM before_deleted_at)) AND operator_access_version IS NOT NULL AND "
            "operator_access_version>0 AND operator_access_active IS TRUE AND reason "
            "IS NOT NULL AND length(reason) BETWEEN 1 AND 1000 AND reason ~ '[^[:spac"
            "e:]]' AND workflow_id IS NULL OR (operation='delete' AND actor_id=accoun"
            "t_id AND before_deleted_at IS NULL AND after_deleted_at IS NOT NULL AND "
            "after_deleted_at=changed_at AND after_banned_at IS NOT DISTINCT FROM bef"
            "ore_banned_at AND operator_access_version IS NULL AND operator_access_ac"
            "tive IS NULL AND reason IS NULL AND workflow_id IS NOT NULL)",
            name=op.f("ck_account_lifecycle_revisions_actual_transition_shape"),
        ),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND span"
            "_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('"
            "0', 32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))",
            name=op.f("ck_account_lifecycle_revisions_origin_trace_pair"),
        ),
        sa.CheckConstraint(
            "operation IN ('ban','unban','delete')",
            name=op.f("ck_account_lifecycle_revisions_finite_operation"),
        ),
        sa.CheckConstraint(
            "(previous_version IS NULL AND version=1) OR (previous_version IS NOT NUL"
            "L AND previous_version>0 AND version=previous_version+1)",
            name=op.f("ck_account_lifecycle_revisions_consecutive_source_version"),
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL A"
            "ND span_id IS NULL)",
            name=op.f("ck_account_lifecycle_revisions_origin_request_context"),
        ),
        sa.CheckConstraint(
            "version>0", name=op.f("ck_account_lifecycle_revisions_positive_source_version")
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "previous_version"],
            ["account_lifecycle_revisions.account_id", "account_lifecycle_revisions.version"],
            name="fk_lifecycle_previous_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_account_lifecycle_revisions_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id", "operator_access_version", "operator_access_active"],
            [
                "operator_access_revisions.account_id",
                "operator_access_revisions.version",
                "operator_access_revisions.active",
            ],
            name="fk_lifecycle_actual_operator_grant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_account_lifecycle_revisions_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_session_id", "actor_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_lifecycle_actual_actor_session",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id", "account_id", "actor_session_id"],
            [
                "account_deletion_workflows.id",
                "account_deletion_workflows.account_id",
                "account_deletion_workflows.session_id",
            ],
            name="fk_lifecycle_actual_deletion_workflow",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_lifecycle_revisions")),
        sa.UniqueConstraint("account_id", "version", name="uq_lifecycle_source_version"),
        sa.UniqueConstraint(
            "id", "account_id", "actor_id", "operation", name="uq_lifecycle_source_intent_scope"
        ),
        sa.UniqueConstraint(
            "id",
            "actor_id",
            "account_id",
            "version",
            "operation",
            name="uq_lifecycle_source_canonical",
        ),
        sa.UniqueConstraint("id", "actor_session_id", name="uq_lifecycle_source_session"),
        sa.UniqueConstraint("id", "workflow_id", name="uq_lifecycle_source_workflow"),
    )
    op.create_table(
        "account_lifecycle_intents",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=6), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("target_account_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_session_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_workflow_id", sa.Uuid(), nullable=True),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("result_kind", sa.String(length=7), nullable=False),
        sa.Column("result_source_id", sa.Uuid(), nullable=True),
        sa.Column("noop_source_version", sa.Integer(), nullable=True),
        sa.Column("noop_banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("noop_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "(operation IN ('ban','unban') AND submitted_workflow_id IS NULL) OR (ope"
            "ration='delete' AND actor_id=target_account_id AND submitted_workflow_id"
            " IS NOT NULL AND result_kind='changed')",
            name=op.f("ck_account_lifecycle_intents_owned_operation_shape"),
        ),
        sa.CheckConstraint(
            "(result_kind='changed' AND result_source_id IS NOT NULL AND noop_source_"
            "version IS NULL AND noop_banned_at IS NULL AND noop_deleted_at IS NULL) "
            "OR (result_kind='noop' AND result_source_id IS NULL AND operation IN ('b"
            "an','unban') AND (noop_source_version IS NULL OR noop_source_version>0) "
            "AND ((operation='ban' AND noop_banned_at IS NOT NULL) OR (operation='unb"
            "an' AND noop_banned_at IS NULL)))",
            name=op.f("ck_account_lifecycle_intents_typed_result_snapshot"),
        ),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND span"
            "_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != repeat('"
            "0', 32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0', 16))",
            name=op.f("ck_account_lifecycle_intents_origin_trace_pair"),
        ),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'",
            name=op.f("ck_account_lifecycle_intents_bounded_intent_key"),
        ),
        sa.CheckConstraint(
            "operation IN ('ban','unban','delete')",
            name=op.f("ck_account_lifecycle_intents_finite_operation"),
        ),
        sa.CheckConstraint(
            "result_kind IN ('changed','noop')",
            name=op.f("ck_account_lifecycle_intents_finite_result_kind"),
        ),
        sa.CheckConstraint(
            "http_request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL A"
            "ND span_id IS NULL)",
            name=op.f("ck_account_lifecycle_intents_origin_request_context"),
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint)=32",
            name=op.f("ck_account_lifecycle_intents_actual_payload_hmac"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_account_lifecycle_intents_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_source_id", "submitted_session_id"],
            ["account_lifecycle_revisions.id", "account_lifecycle_revisions.actor_session_id"],
            name="fk_lifecycle_intent_result_session",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_source_id", "submitted_workflow_id"],
            ["account_lifecycle_revisions.id", "account_lifecycle_revisions.workflow_id"],
            name="fk_lifecycle_intent_result_workflow",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_source_id", "target_account_id", "actor_id", "operation"],
            [
                "account_lifecycle_revisions.id",
                "account_lifecycle_revisions.account_id",
                "account_lifecycle_revisions.actor_id",
                "account_lifecycle_revisions.operation",
            ],
            name="fk_lifecycle_intent_actual_result",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_session_id", "actor_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_lifecycle_intent_actual_session",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_workflow_id", "target_account_id", "submitted_session_id"],
            [
                "account_deletion_workflows.id",
                "account_deletion_workflows.account_id",
                "account_deletion_workflows.session_id",
            ],
            name="fk_lifecycle_intent_owned_workflow",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_account_id", "noop_source_version"],
            ["account_lifecycle_revisions.account_id", "account_lifecycle_revisions.version"],
            name="fk_lifecycle_intent_noop_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_account_id"],
            ["accounts.id"],
            name=op.f("fk_account_lifecycle_intents_target_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "actor_id", "operation", "key", name=op.f("pk_account_lifecycle_intents")
        ),
    )
    op.create_index(
        "ix_lifecycle_source_actor_time",
        "account_lifecycle_revisions",
        ["actor_id", "changed_at", "id"],
    )
    op.create_index(
        "ix_lifecycle_intent_actor_time", "account_lifecycle_intents", ["actor_id", "created_at"]
    )
    op.add_column("accounts", sa.Column("lifecycle_version", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_accounts_lifecycle_source_version"),
        "accounts",
        "lifecycle_version IS NULL OR lifecycle_version>0",
    )
    op.create_foreign_key(
        "fk_accounts_current_lifecycle_source",
        "accounts",
        "account_lifecycle_revisions",
        ["id", "lifecycle_version"],
        ["account_id", "version"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    retained = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM account_lifecycle_intents) OR "
            "EXISTS(SELECT 1 FROM account_lifecycle_revisions) OR "
            "EXISTS(SELECT 1 FROM account_deletion_workflows) OR "
            "EXISTS(SELECT 1 FROM accounts WHERE lifecycle_version IS NOT NULL)"
        )
    )
    if retained:
        raise RuntimeError("Refusing to drop retained lifecycle and deletion recovery history")
    op.drop_constraint("fk_accounts_current_lifecycle_source", "accounts", type_="foreignkey")
    op.drop_constraint(op.f("ck_accounts_lifecycle_source_version"), "accounts", type_="check")
    op.drop_column("accounts", "lifecycle_version")
    op.drop_index("ix_lifecycle_intent_actor_time", table_name="account_lifecycle_intents")
    op.drop_table("account_lifecycle_intents")
    op.drop_index("ix_lifecycle_source_actor_time", table_name="account_lifecycle_revisions")
    op.drop_table("account_lifecycle_revisions")
    op.drop_table("account_deletion_workflows")
