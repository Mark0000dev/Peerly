from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base


class AiJobRecord(Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        UniqueConstraint("id", "actor_id", "kind", name="uq_ai_jobs_owner_kind"),
        UniqueConstraint("id", "token", "generation", name="uq_ai_jobs_lease"),
        CheckConstraint(
            "request_id IS NOT NULL OR (action_id IS NULL "
            "AND trace_id IS NULL AND span_id IS NULL)",
            name="origin_request",
        ),
        CheckConstraint(
            "length(btrim(model)) > 0 AND length(btrim(prompt)) > 0 "
            "AND length(btrim(schema_version)) > 0 AND length(btrim(adapter)) > 0",
            name="explicit_versions",
        ),
        CheckConstraint(
            "state != 'running' OR (token IS NOT NULL AND generation > 0 AND attempts > 0)",
            name="running_lease",
        ),
        CheckConstraint(
            "failure IS NULL OR failure IN ('transient','invalid_output','invalid_input',"
            "'timeout','auth_unavailable','rate_limited','account_unavailable',"
            "'stale_source','executor_lost')",
            name="failure",
        ),
        CheckConstraint(
            "(trace_id IS NULL AND span_id IS NULL) OR (trace_id IS NOT NULL "
            "AND span_id IS NOT NULL AND trace_id ~ '^[0-9a-f]{32}$' "
            "AND trace_id != repeat('0',32) AND span_id ~ '^[0-9a-f]{16}$' "
            "AND span_id != repeat('0',16))",
            name="trace_pair",
        ),
        CheckConstraint(
            "kind IN ('clarify_goal','suggest_subject','assess_photo','triage_report')", name="kind"
        ),
        CheckConstraint(
            "state IN ('queued','running','succeeded','failed','cancelled','expired')", name="state"
        ),
        CheckConstraint("octet_length(digest) = 32", name="digest"),
        CheckConstraint("octet_length(input_json) <= 32768", name="input_bound"),
        CheckConstraint(
            "result_json IS NULL OR octet_length(result_json) <= 16384", name="result_bound"
        ),
        CheckConstraint("(state = 'succeeded') = (result_json IS NOT NULL)", name="result_state"),
        CheckConstraint(
            "attempts BETWEEN 0 AND 3 AND generation >= 0 AND source_version > 0", name="versions"
        ),
        CheckConstraint("deadline > created_at", name="deadline"),
        Index("ix_ai_jobs_due", "state", "not_before", "created_at"),
        Index("ix_ai_jobs_owner", "actor_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(24))
    source_id: Mapped[UUID] = mapped_column()
    source_version: Mapped[int] = mapped_column()
    digest: Mapped[bytes] = mapped_column(LargeBinary)
    input_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[str] = mapped_column(String(100))
    adapter: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column()
    generation: Mapped[int] = mapped_column()
    token: Mapped[UUID | None] = mapped_column()
    failure: Mapped[str | None] = mapped_column(String(32))
    request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))


class AiIntentRecord(Base):
    __tablename__ = "ai_intents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "actor_id", "kind"],
            ["ai_jobs.id", "ai_jobs.actor_id", "ai_jobs.kind"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="key"),
        CheckConstraint("octet_length(digest) = 32", name="digest"),
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(24), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    job_id: Mapped[UUID] = mapped_column()
    digest: Mapped[bytes] = mapped_column(LargeBinary)


class AiBudgetRecord(Base):
    __tablename__ = "ai_actor_budgets"
    __table_args__ = (
        CheckConstraint("tokens >= 0 AND tokens <= 5 AND last_served >= 0", name="bounds"),
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    tokens: Mapped[float] = mapped_column()
    refilled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_served: Mapped[int] = mapped_column()


class AiSlotRecord(Base):
    __tablename__ = "ai_executor_slot"
    __table_args__ = (
        ForeignKeyConstraint(
            ["job_id", "token", "generation"],
            ["ai_jobs.id", "ai_jobs.token", "ai_jobs.generation"],
            name="fk_ai_executor_slot_owned_lease",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            ondelete="RESTRICT",
        ),
        CheckConstraint("circuit IS NULL OR circuit = 'auth_unavailable'", name="circuit"),
        CheckConstraint(
            "id = 1 AND generation >= 0 AND sequence >= 0 AND interactive_streak BETWEEN 0 AND 4",
            name="singleton",
        ),
        CheckConstraint(
            "(token IS NULL) = (job_id IS NULL) AND (token IS NULL) = (lease_until IS NULL)",
            name="lease_shape",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    generation: Mapped[int] = mapped_column()
    sequence: Mapped[int] = mapped_column()
    interactive_streak: Mapped[int] = mapped_column()
    token: Mapped[UUID | None] = mapped_column()
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("ai_jobs.id", ondelete="RESTRICT"))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    circuit: Mapped[str | None] = mapped_column(String(32))
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiAttemptRecord(Base):
    __tablename__ = "ai_attempts"
    __table_args__ = (
        CheckConstraint("generation > 0 AND number BETWEEN 1 AND 3", name="bounds"),
        CheckConstraint("(outcome IS NULL) = (ended_at IS NULL)", name="outcome_time"),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('succeeded','failed','cancelled','expired',"
            "'transient','invalid_output','invalid_input','timeout','auth_unavailable',"
            "'rate_limited','account_unavailable','stale_source','executor_lost')",
            name="outcome",
        ),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="times"),
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_jobs.id", ondelete="RESTRICT"), primary_key=True
    )
    number: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[UUID] = mapped_column(unique=True)
    generation: Mapped[int] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(32))


AI_MODELS: tuple[type[Base], ...] = (
    AiJobRecord,
    AiIntentRecord,
    AiBudgetRecord,
    AiSlotRecord,
    AiAttemptRecord,
)
