"""Published policies and explicit registration contexts and receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_registration"
down_revision: str | Sequence[str] | None = "0003_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('terms', 'privacy')", name=op.f("ck_policy_documents_known_kind")
        ),
        sa.CheckConstraint(
            "version ~ '^[A-Za-z0-9._-]{1,64}$'", name=op.f("ck_policy_documents_valid_version")
        ),
        sa.CheckConstraint(
            "length(btrim(title)) > 0 AND length(btrim(content)) > 0",
            name=op.f("ck_policy_documents_actual_content"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_documents")),
        sa.UniqueConstraint("id", "kind", name="uq_policy_documents_id_kind"),
        sa.UniqueConstraint("kind", "version", name="uq_policy_documents_kind_version"),
    )
    op.create_index(
        "ix_policy_documents_publication",
        "policy_documents",
        ["kind", "published_at", "id"],
        unique=False,
    )
    op.create_table(
        "registration_contexts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("terms_id", sa.Uuid(), nullable=False),
        sa.Column("privacy_id", sa.Uuid(), nullable=False),
        sa.Column("terms_kind", sa.String(length=16), nullable=False),
        sa.Column("privacy_kind", sa.String(length=16), nullable=False),
        sa.Column("notice_text", sa.String(length=512), nullable=False),
        sa.Column("surface", sa.String(length=32), nullable=False),
        sa.Column("intent_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "surface = 'onboarding_completion'", name=op.f("ck_registration_contexts_known_surface")
        ),
        sa.CheckConstraint(
            "terms_kind = 'terms' AND privacy_kind = 'privacy'",
            name=op.f("ck_registration_contexts_correct_document_kinds"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name=op.f("ck_registration_contexts_valid_completion"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_registration_contexts_valid_expiry")
        ),
        sa.CheckConstraint(
            "length(btrim(notice_text)) > 0", name=op.f("ck_registration_contexts_actual_notice")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_registration_contexts_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["privacy_id", "privacy_kind"],
            ["policy_documents.id", "policy_documents.kind"],
            name="fk_registration_contexts_privacy_document",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "account_id"],
            ["sessions.id", "sessions.account_id"],
            name="fk_registration_contexts_session_account",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["terms_id", "terms_kind"],
            ["policy_documents.id", "policy_documents.kind"],
            name="fk_registration_contexts_terms_document",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registration_contexts")),
        sa.UniqueConstraint(
            "account_id", "intent_key", name="uq_registration_contexts_account_intent"
        ),
        sa.UniqueConstraint(
            "id", "account_id", "completed_at", name="uq_registration_contexts_actual_completion"
        ),
    )
    op.create_table(
        "registration_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("context_id", sa.Uuid(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("intent_key", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_registration_receipts_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["context_id", "account_id", "registered_at"],
            [
                "registration_contexts.id",
                "registration_contexts.account_id",
                "registration_contexts.completed_at",
            ],
            name="fk_registration_receipts_actual_completion",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registration_receipts")),
        sa.UniqueConstraint("account_id", name="uq_registration_receipts_account_id"),
        sa.UniqueConstraint("context_id", name="uq_registration_receipts_context_id"),
    )


def downgrade() -> None:
    op.drop_table("registration_receipts")
    op.drop_table("registration_contexts")
    op.drop_index("ix_policy_documents_publication", table_name="policy_documents")
    op.drop_table("policy_documents")
