"""Retained selected profile references and private report intents."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_profile_reports"
down_revision: str | Sequence[str] | None = "0019_discovery_freshness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profile_access_contexts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("viewer_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("photo_version", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=True),
        sa.Column("goal_version", sa.Integer(), nullable=True),
        sa.Column("help_version", sa.Integer(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(goal_id IS NULL AND goal_version IS NULL) OR "
            "(goal_id IS NOT NULL AND goal_version IS NOT NULL AND goal_version > 0)",
            name=op.f("ck_profile_access_contexts_goal_reference_shape"),
        ),
        sa.CheckConstraint(
            "help_version IS NULL OR help_version > 0",
            name=op.f("ck_profile_access_contexts_help_version"),
        ),
        sa.CheckConstraint(
            "profile_version > 0 AND photo_version > 0",
            name=op.f("ck_profile_access_contexts_positive_versions"),
        ),
        sa.CheckConstraint(
            "viewer_id != target_id", name=op.f("ck_profile_access_contexts_distinct_participants")
        ),
        sa.ForeignKeyConstraint(
            ["target_id", "goal_id", "goal_version"],
            ["goal_revisions.account_id", "goal_revisions.goal_id", "goal_revisions.version"],
            name=op.f("fk_profile_access_contexts_target_id_goal_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_id", "help_version"],
            ["help_revisions.account_id", "help_revisions.version"],
            name=op.f("fk_profile_access_contexts_target_id_help_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_id", "photo_version"],
            ["photo_revisions.account_id", "photo_revisions.version"],
            name=op.f("fk_profile_access_contexts_target_id_photo_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_id", "profile_version"],
            ["profile_revisions.account_id", "profile_revisions.version"],
            name=op.f("fk_profile_access_contexts_target_id_profile_revisions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["accounts.id"],
            name=op.f("fk_profile_access_contexts_target_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["viewer_id"],
            ["accounts.id"],
            name=op.f("fk_profile_access_contexts_viewer_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_access_contexts")),
        sa.UniqueConstraint("id", "viewer_id", name="uq_profile_access_contexts_viewer"),
    )
    op.create_index(
        "ix_profile_access_contexts_viewer_issued",
        "profile_access_contexts",
        ["viewer_id", "issued_at", "id"],
        unique=False,
    )
    op.create_table(
        "profile_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reporter_id", sa.Uuid(), nullable=False),
        sa.Column("context_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("comment", sa.String(length=1000), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category != 'other' OR comment IS NOT NULL",
            name=op.f("ck_profile_reports_other_explanation"),
        ),
        sa.CheckConstraint(
            "category IN ('impersonation','harassment','inappropriate_content','spam','other')",
            name=op.f("ck_profile_reports_known_category"),
        ),
        sa.CheckConstraint(
            "comment IS NULL OR length(comment) BETWEEN 1 AND 1000",
            name=op.f("ck_profile_reports_comment_length"),
        ),
        sa.ForeignKeyConstraint(
            ["context_id", "reporter_id"],
            ["profile_access_contexts.id", "profile_access_contexts.viewer_id"],
            name=op.f("fk_profile_reports_context_id_profile_access_contexts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["accounts.id"],
            name=op.f("fk_profile_reports_reporter_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_reports")),
        sa.UniqueConstraint("id", "reporter_id", name="uq_profile_reports_reporter"),
    )
    op.create_index(
        "ix_profile_reports_reporter_submitted",
        "profile_reports",
        ["reporter_id", "submitted_at", "id"],
        unique=False,
    )
    op.create_table(
        "profile_report_intents",
        sa.Column("reporter_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "key ~ '^[A-Za-z0-9_-]{8,128}$'",
            name=op.f("ck_profile_report_intents_intent_key_shape"),
        ),
        sa.CheckConstraint(
            "octet_length(fingerprint) = 32",
            name=op.f("ck_profile_report_intents_fingerprint_length"),
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "reporter_id"],
            ["profile_reports.id", "profile_reports.reporter_id"],
            name=op.f("fk_profile_report_intents_report_id_profile_reports"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_id"],
            ["accounts.id"],
            name=op.f("fk_profile_report_intents_reporter_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("reporter_id", "key", name=op.f("pk_profile_report_intents")),
    )


def downgrade() -> None:
    retained = op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM profile_access_contexts)")
    )
    if retained:
        raise RuntimeError("Cannot downgrade retained profile safety history")
    op.drop_table("profile_report_intents")
    op.drop_index("ix_profile_reports_reporter_submitted", table_name="profile_reports")
    op.drop_table("profile_reports")
    op.drop_index("ix_profile_access_contexts_viewer_issued", table_name="profile_access_contexts")
    op.drop_table("profile_access_contexts")
