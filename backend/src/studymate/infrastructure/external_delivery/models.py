"""Reference-only captures and retained, bounded per-sink delivery metadata."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from studymate.infrastructure.persistence.base import Base

SINKS_SQL = "('umami','telegram_support')"
FAILURES_SQL = (
    "('transient','rate_limited','credentials_unavailable','destination_un"
    "available','invalid_response','timeout','lease_expired','cancelled','"
    "permanent')"
)


class DeliveryDestinationRecord(Base):
    __tablename__ = "external_delivery_destinations"
    __table_args__ = (
        CheckConstraint(f"sink IN {SINKS_SQL}", name="known_sink"),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("octet_length(fingerprint)=32", name="destination_fingerprint"),
    )
    sink: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeliverySourceRecord(Base):
    __tablename__ = "external_delivery_sources"
    __table_args__ = (
        UniqueConstraint("canonical_event_id", name="uq_external_sources_canonical"),
        UniqueConstraint("observation_id", name="uq_external_sources_observation"),
        UniqueConstraint("support_case_id", name="uq_external_sources_support"),
        CheckConstraint(
            "(source_kind='canonical' AND canonical_event_id IS NOT NULL "
            "AND observation_id IS NULL AND support_case_id IS NULL) OR "
            "(source_kind='client_observation' AND observation_id IS NOT NULL "
            "AND canonical_event_id IS NULL AND support_case_id IS NULL) OR "
            "(source_kind='support_case' AND support_case_id IS NOT NULL "
            "AND canonical_event_id IS NULL AND observation_id IS NULL)",
            name="actual_source_shape",
        ),
        CheckConstraint("mode IN ('live','backfill_umami')", name="known_mode"),
        CheckConstraint("routing_version=1", name="known_routing_version"),
        CheckConstraint(
            "(materialized_at IS NULL AND exclusion_reason IS NULL) OR "
            "(materialized_at IS NOT NULL AND materialized_at>=captured_at "
            "AND exclusion_reason IS NOT NULL "
            "AND exclusion_reason IN ('none','backfill_not_analytics'))",
            name="actual_materialization",
        ),
        Index(
            "ix_external_sources_unrouted",
            "captured_at",
            "id",
            postgresql_where=text("materialized_at IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    source_kind: Mapped[str] = mapped_column(String(32))
    canonical_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("product_events.id", ondelete="RESTRICT")
    )
    observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("client_observations.id", ondelete="RESTRICT")
    )
    support_case_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("support_cases.id", ondelete="RESTRICT")
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    mode: Mapped[str] = mapped_column(String(24), server_default=text("'live'"))
    routing_version: Mapped[int] = mapped_column(server_default=text("1"))
    materialized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exclusion_reason: Mapped[str | None] = mapped_column(String(32))


class ExternalDeliveryRecord(Base):
    __tablename__ = "external_deliveries"
    __table_args__ = (
        UniqueConstraint("source_id", "sink", name="uq_external_deliveries_source_sink"),
        ForeignKeyConstraint(
            ["sink", "destination_revision"],
            ["external_delivery_destinations.sink", "external_delivery_destinations.revision"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"sink IN {SINKS_SQL}", name="known_sink"),
        CheckConstraint("projection_version=1", name="known_projection_version"),
        CheckConstraint(
            "state IN ('pending','leased','retry','succeeded','dead')", name="known_state"
        ),
        CheckConstraint("attempt_count BETWEEN 0 AND 8", name="bounded_attempts"),
        CheckConstraint(
            "destination_revision IS NOT NULL OR (state='pending' AND attempt_count=0)",
            name="durable_destination",
        ),
        CheckConstraint(
            (
                "(state='leased' AND lease_id IS NOT NULL AND lease_until IS NOT NULL "
                "AND destination_revision IS NOT NULL AND attempt_count>0) OR "
                "(state!='leased' AND lease_id IS NULL AND lease_until IS NULL)"
            ),
            name="actual_lease",
        ),
        CheckConstraint(
            (
                "(state='succeeded' AND delivered_at IS NOT NULL) OR "
                "(state!='succeeded' AND delivered_at IS NULL)"
            ),
            name="actual_delivery",
        ),
        CheckConstraint(
            "(state='pending' AND attempt_count=0) OR (state!='pending' AND attempt_count>0)",
            name="actual_attempt_count",
        ),
        CheckConstraint(
            "delivered_at IS NULL OR (delivered_at>=created_at AND updated_at>=delivered_at)",
            name="ordered_delivery",
        ),
        CheckConstraint("updated_at>=created_at", name="ordered_update"),
        CheckConstraint(
            f"last_failure IS NULL OR last_failure IN {FAILURES_SQL}", name="known_failure"
        ),
        CheckConstraint(
            (
                "provider_message_id IS NULL OR (sink='telegram_support' "
                "AND state='succeeded' AND provider_message_id>0)"
            ),
            name="actual_message_receipt",
        ),
        Index(
            "ix_external_deliveries_due",
            "sink",
            "next_attempt_at",
            "id",
            postgresql_where=text("state IN ('pending','retry')"),
        ),
        Index(
            "ix_external_deliveries_lease",
            "lease_until",
            "id",
            postgresql_where=text("state='leased'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_delivery_sources.id", ondelete="RESTRICT")
    )
    sink: Mapped[str] = mapped_column(String(32))
    destination_revision: Mapped[int | None] = mapped_column()
    projection_version: Mapped[int] = mapped_column()
    state: Mapped[str] = mapped_column(String(16))
    attempt_count: Mapped[int] = mapped_column()
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_id: Mapped[UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[int | None] = mapped_column(BigInteger)
    last_failure: Mapped[str | None] = mapped_column(String(32))


class DeliveryAttemptRecord(Base):
    __tablename__ = "external_delivery_attempts"
    __table_args__ = (
        UniqueConstraint("lease_id", name="uq_external_delivery_attempts_lease"),
        CheckConstraint("attempt_no BETWEEN 1 AND 8", name="bounded_attempt"),
        CheckConstraint(
            (
                "(ended_at IS NULL AND outcome IS NULL) OR (ended_at IS NOT NULL AND "
                "ended_at>=started_at AND outcome IS NOT NULL AND outcome IN "
                "('accepted','retryable','ambiguous','permanent','lease_expired'))"
            ),
            name="actual_attempt_outcome",
        ),
        CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599", name="bounded_status"
        ),
        CheckConstraint(
            ("retry_after_seconds IS NULL OR retry_after_seconds BETWEEN 1 AND 2147483647"),
            name="positive_retry",
        ),
        CheckConstraint(
            "provider_message_id IS NULL OR provider_message_id>0", name="actual_message_receipt"
        ),
        CheckConstraint(f"failure IS NULL OR failure IN {FAILURES_SQL}", name="known_failure"),
        CheckConstraint(
            "late_ack_at IS NULL OR (ended_at IS NOT NULL AND late_ack_at>=ended_at)",
            name="actual_late_ack",
        ),
        CheckConstraint(
            "late_message_id IS NULL OR (late_message_id>0 AND late_ack_at IS NOT NULL)",
            name="actual_late_message",
        ),
        CheckConstraint(
            "(ended_at IS NULL AND failure IS NULL AND http_status IS NULL "
            "AND retry_after_seconds IS NULL AND provider_message_id IS NULL) OR "
            "(ended_at IS NOT NULL AND ((outcome='accepted' AND failure IS NULL) "
            "OR (outcome!='accepted' AND failure IS NOT NULL)))",
            name="closed_result_shape",
        ),
        Index(
            "ix_external_delivery_attempts_source_time", "started_at", "delivery_id", "attempt_no"
        ),
    )
    delivery_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_deliveries.id", ondelete="RESTRICT"), primary_key=True
    )
    attempt_no: Mapped[int] = mapped_column(primary_key=True)
    lease_id: Mapped[UUID] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(24))
    failure: Mapped[str | None] = mapped_column(String(32))
    http_status: Mapped[int | None] = mapped_column()
    retry_after_seconds: Mapped[int | None] = mapped_column()
    provider_message_id: Mapped[int | None] = mapped_column(BigInteger)
    late_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    late_message_id: Mapped[int | None] = mapped_column(BigInteger)


class DeliveryScheduleRecord(Base):
    __tablename__ = "external_delivery_schedule"
    __table_args__ = (
        CheckConstraint(f"sink IN {SINKS_SQL}", name="known_sink"),
        CheckConstraint("turn BETWEEN 0 AND 1", name="bounded_turn"),
        UniqueConstraint("turn", name="uq_external_delivery_schedule_turn"),
        CheckConstraint(
            f"blocked_reason IS NULL OR blocked_reason IN {FAILURES_SQL}", name="known_block"
        ),
    )
    sink: Mapped[str] = mapped_column(String(32), primary_key=True)
    turn: Mapped[int] = mapped_column()
    next_claim_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocked_reason: Mapped[str | None] = mapped_column(String(32))
