"""Bounded retained AI jobs, owned leases and singleton admission; no live executor."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_ai_queue"
down_revision: str | Sequence[str] | None = "0016_product_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("digest", sa.LargeBinary(), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt", sa.String(length=100), nullable=False),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("adapter", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("token", sa.Uuid(), nullable=True),
        sa.Column("failure", sa.String(length=32), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.CheckConstraint("deadline > created_at", name=op.f("ck_ai_jobs_deadline")),
        sa.CheckConstraint("octet_length(digest) = 32", name=op.f("ck_ai_jobs_digest")),
        sa.CheckConstraint(
            "length(btrim(model)) > 0 AND length(btrim(prompt)) > 0 AND "
            "length(btrim(schema_version)) > 0 AND length(btrim(adapter)) > 0",
            name=op.f("ck_ai_jobs_explicit_versions"),
        ),
        sa.CheckConstraint(
            "failure IS NULL OR failure IN ('transient','invalid_output',"
            "'invalid_input','timeout','auth_unavailable','rate_limited',"
            "'account_unavailable','stale_source','executor_lost')",
            name=op.f("ck_ai_jobs_failure"),
        ),
        sa.CheckConstraint(
            "octet_length(input_json) <= 32768", name=op.f("ck_ai_jobs_input_bound")
        ),
        sa.CheckConstraint(
            "kind IN ('clarify_goal','suggest_subject','assess_photo','triage_report')",
            name=op.f("ck_ai_jobs_kind"),
        ),
        sa.CheckConstraint(
            "request_id IS NOT NULL OR (action_id IS NULL AND trace_id IS NULL AND "
            "span_id IS NULL)",
            name=op.f("ck_ai_jobs_origin_request"),
        ),
        sa.CheckConstraint(
            "result_json IS NULL OR octet_length(result_json) <= 16384",
            name=op.f("ck_ai_jobs_result_bound"),
        ),
        sa.CheckConstraint(
            "(state = 'succeeded') = (result_json IS NOT NULL)",
            name=op.f("ck_ai_jobs_result_state"),
        ),
        sa.CheckConstraint(
            "state != 'running' OR (token IS NOT NULL AND generation > 0 AND attempts > 0)",
            name=op.f("ck_ai_jobs_running_lease"),
        ),
        sa.CheckConstraint(
            "state IN ('queued','running','succeeded','failed','cancelled','expired')",
            name=op.f("ck_ai_jobs_state"),
        ),
        sa.CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL AND "
            "span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' AND trace_id != "
            "repeat('0',32) AND span_id ~ '^[0-9a-f]{16}$' AND span_id != repeat('0',"
            "16))",
            name=op.f("ck_ai_jobs_trace_pair"),
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 3 AND generation >= 0 AND source_version > 0",
            name=op.f("ck_ai_jobs_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_ai_jobs_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_jobs")),
        sa.UniqueConstraint("id", "token", "generation", name=op.f("uq_ai_jobs_lease")),
        sa.UniqueConstraint("id", "actor_id", "kind", name=op.f("uq_ai_jobs_owner_kind")),
    )
    op.create_index(
        "ix_ai_jobs_due", "ai_jobs", ["state", "not_before", "created_at"], unique=False
    )
    op.create_index("ix_ai_jobs_owner", "ai_jobs", ["actor_id", "created_at"], unique=False)
    op.create_table(
        "ai_intents",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("digest", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("octet_length(digest) = 32", name=op.f("ck_ai_intents_digest")),
        sa.CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name=op.f("ck_ai_intents_key")),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_ai_intents_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "actor_id", "kind"],
            ["ai_jobs.id", "ai_jobs.actor_id", "ai_jobs.kind"],
            name=op.f("fk_ai_intents_job_id_ai_jobs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("actor_id", "kind", "key", name=op.f("pk_ai_intents")),
    )
    op.create_table(
        "ai_actor_budgets",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("tokens", sa.Double(), nullable=False),
        sa.Column("refilled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_served", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "tokens >= 0 AND tokens <= 5 AND last_served >= 0",
            name=op.f("ck_ai_actor_budgets_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["accounts.id"],
            name=op.f("fk_ai_actor_budgets_actor_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("actor_id", name=op.f("pk_ai_actor_budgets")),
    )
    op.create_table(
        "ai_executor_slot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("interactive_streak", sa.Integer(), nullable=False),
        sa.Column("token", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("circuit", sa.String(length=32), nullable=True),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "circuit IS NULL OR circuit = 'auth_unavailable'",
            name=op.f("ck_ai_executor_slot_circuit"),
        ),
        sa.CheckConstraint(
            "(token IS NULL) = (job_id IS NULL) AND (token IS NULL) = (lease_until IS NULL)",
            name=op.f("ck_ai_executor_slot_lease_shape"),
        ),
        sa.CheckConstraint(
            "id = 1 AND generation >= 0 AND sequence >= 0 AND interactive_streak BETWEEN 0 AND 4",
            name=op.f("ck_ai_executor_slot_singleton"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ai_jobs.id"],
            name=op.f("fk_ai_executor_slot_job_id_ai_jobs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_executor_slot")),
    )
    op.create_table(
        "ai_attempts",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("token", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "generation > 0 AND number BETWEEN 1 AND 3", name=op.f("ck_ai_attempts_bounds")
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('succeeded','failed','cancelled',"
            "'expired','transient','invalid_output','invalid_input','timeout',"
            "'auth_unavailable','rate_limited','account_unavailable','stale_source',"
            "'executor_lost')",
            name=op.f("ck_ai_attempts_outcome"),
        ),
        sa.CheckConstraint(
            "(outcome IS NULL) = (ended_at IS NULL)", name=op.f("ck_ai_attempts_outcome_time")
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at", name=op.f("ck_ai_attempts_times")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ai_jobs.id"],
            name=op.f("fk_ai_attempts_job_id_ai_jobs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("job_id", "number", name=op.f("pk_ai_attempts")),
        sa.UniqueConstraint("token", name=op.f("uq_ai_attempts_token")),
    )
    slot = sa.table(
        "ai_executor_slot",
        sa.column("id", sa.Integer()),
        sa.column("generation", sa.Integer()),
        sa.column("sequence", sa.Integer()),
        sa.column("interactive_streak", sa.Integer()),
    )
    op.bulk_insert(slot, [{"id": 1, "generation": 0, "sequence": 0, "interactive_streak": 0}])
    # Seed before adding the deferred FK: upgrade/downgrade in one transaction
    # must not leave pending trigger events on the singleton table.
    op.create_foreign_key(
        "fk_ai_executor_slot_owned_lease",
        "ai_executor_slot",
        "ai_jobs",
        ["job_id", "token", "generation"],
        ["id", "token", "generation"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint("fk_ai_executor_slot_owned_lease", "ai_executor_slot", type_="foreignkey")
    op.drop_table("ai_attempts")
    op.drop_table("ai_executor_slot")
    op.drop_table("ai_actor_budgets")
    op.drop_table("ai_intents")
    op.drop_table("ai_jobs")
