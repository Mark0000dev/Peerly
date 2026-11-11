"""Fresh worker readiness on the existing singleton; never release execution capacity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051_ai_runtime_health"
down_revision: str | Sequence[str] | None = "0050_bootstrap_catalogue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ai_executor_slot", sa.Column("runtime_worker_id", sa.Uuid(), nullable=True))
    op.add_column(
        "ai_executor_slot",
        sa.Column("runtime_state", sa.String(16), nullable=False, server_default="stopped"),
    )
    for name in ("runtime_started_at", "runtime_heartbeat_at", "runtime_valid_until"):
        op.add_column(
            "ai_executor_slot", sa.Column(name, sa.DateTime(timezone=True), nullable=True)
        )
    for name in ("runtime_model", "runtime_prompt", "runtime_schema", "runtime_adapter"):
        op.add_column("ai_executor_slot", sa.Column(name, sa.String(100), nullable=True))
    op.create_check_constraint(
        "runtime_shape",
        "ai_executor_slot",
        "(runtime_state='stopped' AND runtime_worker_id IS NULL AND runtime_started_at IS"
        " NULL AND runtime_heartbeat_at IS NULL AND runtime_valid_until IS NULL AND runti"
        "me_model IS NULL AND runtime_prompt IS NULL AND runtime_schema IS NULL AND runti"
        "me_adapter IS NULL) OR (runtime_state IN ('starting','ready','blocked') AND runt"
        "ime_worker_id IS NOT NULL AND runtime_started_at IS NOT NULL AND runtime_heartbe"
        "at_at IS NOT NULL AND runtime_valid_until IS NOT NULL AND runtime_model IS NOT N"
        "ULL AND runtime_prompt IS NOT NULL AND runtime_schema IS NOT NULL AND runtime_ad"
        "apter IS NOT NULL)",
    )
    op.create_check_constraint(
        "runtime_clock",
        "ai_executor_slot",
        "runtime_worker_id IS NULL OR (runtime_heartbeat_at>=runtime_started_at AND runti"
        "me_valid_until=runtime_heartbeat_at+interval '15 seconds')",
    )
    op.create_check_constraint(
        "runtime_versions",
        "ai_executor_slot",
        "runtime_worker_id IS NULL OR (length(btrim(runtime_model)) BETWEEN 1 AND 100 AND"
        " length(btrim(runtime_prompt)) BETWEEN 1 AND 100 AND length(btrim(runtime_schema"
        ")) BETWEEN 1 AND 100 AND length(btrim(runtime_adapter)) BETWEEN 1 AND 100)",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM ai_executor_slot WHERE runtime_state<>'stopped')")
    ):
        raise RuntimeError("Stop and confirm the runtime before removing its readiness fencing")
    for name in ("runtime_versions", "runtime_clock", "runtime_shape"):
        op.drop_constraint(op.f("ck_ai_executor_slot_" + name), "ai_executor_slot", type_="check")
    for name in (
        "runtime_adapter",
        "runtime_schema",
        "runtime_prompt",
        "runtime_model",
        "runtime_valid_until",
        "runtime_heartbeat_at",
        "runtime_started_at",
        "runtime_state",
        "runtime_worker_id",
    ):
        op.drop_column("ai_executor_slot", name)
