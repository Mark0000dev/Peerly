"""Durable registered notification transports and per-device delivery receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064_notification_subscriptions"
down_revision: str | Sequence[str] | None = "0063_student_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_student_notification_owned_delivery",
        "student_notification_deliveries",
        ["id", "recipient_id"],
    )
    op.create_table(
        "student_notification_subscriptions",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("enrolled_session_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(8), nullable=False),
        sa.Column("timezone", sa.String(100)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("endpoint_digest", sa.LargeBinary(32)),
        sa.Column("sealed_material", sa.LargeBinary()),
        sa.Column("material_digest", sa.LargeBinary(32)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "installation_id"),
        sa.UniqueConstraint("endpoint_digest", name="uq_student_notification_transport_owner"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(
            ["enrolled_session_id", "account_id"], ["sessions.id", "sessions.account_id"]
        ),
        sa.CheckConstraint("version > 0", name="positive_version"),
        sa.CheckConstraint(
            "endpoint_digest IS NULL OR octet_length(endpoint_digest)=32",
            name="endpoint_digest_shape",
        ),
        sa.CheckConstraint("platform IN ('web','ios','android')", name="known_platform"),
        sa.CheckConstraint(
            "(enabled AND sealed_material IS NOT NULL AND endpoint_digest IS NOT NULL) OR "
            "(NOT enabled AND sealed_material IS NULL AND endpoint_digest IS NULL)",
            name="enabled_material",
        ),
    )
    op.create_table(
        "student_notification_subscription_intents",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.LargeBinary(32), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(8), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("result_enabled", sa.Boolean(), nullable=False),
        sa.Column("result_timezone", sa.String(100)),
        sa.Column("result_fingerprint", sa.String(64)),
        sa.PrimaryKeyConstraint("account_id", "key"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(
            ["account_id", "installation_id"],
            [
                "student_notification_subscriptions.account_id",
                "student_notification_subscriptions.installation_id",
            ],
        ),
        sa.CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_shape"),
        sa.CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="intent_key_shape"),
        sa.CheckConstraint("result_version > 0", name="positive_result_version"),
    )
    op.create_table(
        "student_notification_device_attempts",
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("delivery_id", "account_id", "installation_id"),
        sa.ForeignKeyConstraint(
            ["delivery_id", "account_id"],
            [
                "student_notification_deliveries.id",
                "student_notification_deliveries.recipient_id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "installation_id"],
            [
                "student_notification_subscriptions.account_id",
                "student_notification_subscriptions.installation_id",
            ],
        ),
        sa.CheckConstraint("generation BETWEEN 1 AND 3", name="bounded_device_generation"),
        sa.CheckConstraint(
            "state IN ('sending','accepted','retryable','rejected','unknown')",
            name="known_device_outcome",
        ),
    )


def downgrade() -> None:
    op.drop_table("student_notification_device_attempts")
    op.drop_table("student_notification_subscription_intents")
    op.drop_table("student_notification_subscriptions")
    op.drop_constraint(
        "uq_student_notification_owned_delivery",
        "student_notification_deliveries",
        type_="unique",
    )
