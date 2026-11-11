"""Retained typed observation claims, separate from canonical ProductEvents."""

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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from studymate.infrastructure.persistence.base import Base

_COMMON_OPTIONALS = (
    "action",
    "outcome",
    "metric",
    "value",
    "category",
    "method",
    "route",
    "status_class",
    "duration_ms",
    "request_id",
    "action_id",
    "trace_id",
    "quality_reason",
    "quality_count",
)


def _shape(kind: str, required: tuple[str, ...], allowed: tuple[str, ...] = ()) -> str:
    clauses = [f"kind='{kind}'"]
    clauses.extend(f"{column} IS NOT NULL" for column in required)
    clauses.extend(
        f"{column} IS NULL" for column in _COMMON_OPTIONALS if column not in (*required, *allowed)
    )
    return "(" + " AND ".join(clauses) + ")"


OBSERVATION_SHAPE = " OR ".join(
    (
        _shape("screen.viewed", ()),
        _shape("quality.observed", ("quality_reason", "quality_count")),
        _shape("action.observed", ("action", "outcome"), ("action_id",)),
        _shape("performance.observed", ("metric", "value")),
        _shape("error.observed", ("category",)),
        _shape(
            "http.observed",
            ("method", "route", "status_class", "duration_ms"),
            ("request_id", "action_id", "trace_id"),
        ),
    )
)


class ObservationBatchRecord(Base):
    __tablename__ = "client_observation_batches"
    __table_args__ = (
        CheckConstraint("schema_version=1", name="known_schema"),
        CheckConstraint("key ~ '^[A-Za-z0-9_-]{8,128}$'", name="valid_key"),
        CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_length"),
        CheckConstraint(
            "release_id IS NULL OR release_id ~ '^[0-9a-f]{40}$'", name="release_shape"
        ),
        CheckConstraint(
            "cardinality(accepted_ids)+cardinality(duplicate_ids) BETWEEN 1 AND 20",
            name="bounded_receipt",
        ),
        CheckConstraint("NOT accepted_ids && duplicate_ids", name="disjoint_receipt"),
        Index("ix_client_observation_batches_actor_received", "account_id", "received_at"),
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    schema_version: Mapped[int] = mapped_column()
    release_id: Mapped[str | None] = mapped_column(String(40))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid))
    duplicate_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid))


class ClientObservationRecord(Base):
    __tablename__ = "client_observations"
    __table_args__ = (
        UniqueConstraint("account_id", "event_id", name="uq_client_observations_actor_event"),
        UniqueConstraint("id", "kind", "release_id", name="uq_client_observations_frame_source"),
        ForeignKeyConstraint(
            ["account_id", "batch_key"],
            ["client_observation_batches.account_id", "client_observation_batches.key"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("schema_version=1", name="known_schema"),
        CheckConstraint("octet_length(fingerprint)=32", name="fingerprint_length"),
        CheckConstraint(
            "quality_reason IS NULL OR quality_reason IN "
            "('overflow','invalid','expired','rejected','exhausted','unavailable')",
            name="known_quality_reason",
        ),
        CheckConstraint(
            "quality_count IS NULL OR quality_count BETWEEN 1 AND 65535",
            name="bounded_quality_count",
        ),
        CheckConstraint(OBSERVATION_SHAPE, name="closed_event_shape"),
        CheckConstraint(
            (
                "screen IN ('welcome','verification','onboarding','discover','requ"
                "ests','chats','conversation','profile','study','notifications','s"
                "upport','help','terms','privacy','operator','unknown')"
            ),
            name="known_screen",
        ),
        CheckConstraint(
            (
                "action IS NULL OR action IN ('navigate','submit','retry','cancel'"
                ",'apply','dismiss','load_more','upload','permission_request','ope"
                "n_settings')"
            ),
            name="known_action",
        ),
        CheckConstraint(
            (
                "outcome IS NULL OR outcome IN ('invoked','succeeded_observed','re"
                "jected_observed','failed_observed','cancelled_observed','unknown'"
                ")"
            ),
            name="known_outcome",
        ),
        CheckConstraint(
            "metric IS NULL OR metric IN ('route_ready','lcp','inp','fcp','ttfb','cls')",
            name="known_metric",
        ),
        CheckConstraint(
            (
                "value IS NULL OR (value >= 0 AND value <= CASE WHEN metric='cls' THEN "
                "100 ELSE 60000 END)"
            ),
            name="bounded_metric",
        ),
        CheckConstraint(
            (
                "category IS NULL OR category IN "
                "('network','http','timeout','offline','javascript','render','resource','unknown')"
            ),
            name="known_category",
        ),
        CheckConstraint(
            "method IS NULL OR method IN ('GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS')",
            name="known_method",
        ),
        CheckConstraint(
            (
                "route IS NULL OR route IN ('identity','verification','registratio"
                "n','profile','study','discovery','requests','conversations','medi"
                "a','support','notifications','ai','operator','other')"
            ),
            name="known_route",
        ),
        CheckConstraint(
            (
                "status_class IS NULL OR status_class IN "
                "('1xx','2xx','3xx','4xx','5xx','network','cancelled')"
            ),
            name="known_status_class",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms BETWEEN 0 AND 60000", name="bounded_duration"
        ),
        CheckConstraint(
            "trace_id IS NULL OR (trace_id ~ '^[0-9a-f]{32}$' AND trace_id!=repeat('0',32))",
            name="trace_shape",
        ),
        CheckConstraint(
            "release_id IS NULL OR release_id ~ '^[0-9a-f]{40}$'", name="release_shape"
        ),
        Index("ix_client_observations_actor_received", "account_id", "received_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    event_id: Mapped[UUID] = mapped_column()
    batch_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    schema_version: Mapped[int] = mapped_column()
    release_id: Mapped[str | None] = mapped_column(String(40))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(32))
    screen: Mapped[str] = mapped_column(String(32))
    action: Mapped[str | None] = mapped_column(String(32))
    outcome: Mapped[str | None] = mapped_column(String(32))
    metric: Mapped[str | None] = mapped_column(String(16))
    value: Mapped[float | None] = mapped_column()
    category: Mapped[str | None] = mapped_column(String(16))
    method: Mapped[str | None] = mapped_column(String(8))
    route: Mapped[str | None] = mapped_column(String(32))
    status_class: Mapped[str | None] = mapped_column(String(16))
    duration_ms: Mapped[int | None] = mapped_column()
    request_id: Mapped[UUID | None] = mapped_column()
    action_id: Mapped[UUID | None] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(32))

    quality_reason: Mapped[str | None] = mapped_column(String(16))
    quality_count: Mapped[int | None] = mapped_column()


class ObservationFrameRecord(Base):
    __tablename__ = "client_observation_frames"
    __table_args__ = (
        ForeignKeyConstraint(
            ["observation_id", "kind", "release_id"],
            [
                "client_observations.id",
                "client_observations.kind",
                "client_observations.release_id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("kind='error.observed'", name="actual_error_source"),
        CheckConstraint("frame_index BETWEEN 0 AND 2", name="bounded_index"),
        CheckConstraint("asset_id BETWEEN 0 AND 4095", name="bounded_asset"),
        CheckConstraint(
            "line BETWEEN 1 AND 2147483647 AND column_number BETWEEN 0 AND 2147483647",
            name="bounded_coordinates",
        ),
    )
    observation_id: Mapped[UUID] = mapped_column(primary_key=True)
    frame_index: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    release_id: Mapped[str] = mapped_column(String(40))
    asset_id: Mapped[int] = mapped_column()
    line: Mapped[int] = mapped_column()
    column_number: Mapped[int] = mapped_column()
