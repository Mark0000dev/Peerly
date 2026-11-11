"""Bounded retained operator metadata, including unresolved and zero-route sources."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from studymate.domain.external_delivery.delivery import DeliveryState, FailureCode, ResultKind
from studymate.domain.external_delivery.sources import CapturedSource, CaptureMode, Sink, SourceKind

PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class SourceSummary:
    id: UUID
    kind: SourceKind
    original_id: UUID
    actor_id: UUID | None
    captured_at: datetime
    mode: CaptureMode
    routing_version: int
    materialized_at: datetime | None
    exclusion_reason: str | None


@dataclass(frozen=True, slots=True)
class AttemptSummary:
    attempt_no: int
    lease_id: UUID
    started_at: datetime
    ended_at: datetime | None
    outcome: ResultKind | None
    lease_expired: bool
    failure: FailureCode | None
    http_status: int | None
    retry_after_seconds: int | None
    provider_message_id: int | None
    late_ack_at: datetime | None
    late_message_id: int | None


@dataclass(frozen=True, slots=True)
class DeliverySummary:
    id: UUID
    sink: Sink
    destination_revision: int | None
    projection_version: int
    state: DeliveryState
    next_attempt_at: datetime
    lease_until: datetime | None
    created_at: datetime
    updated_at: datetime
    delivered_at: datetime | None
    provider_message_id: int | None
    last_failure: FailureCode | None
    attempts: tuple[AttemptSummary, ...]


@dataclass(frozen=True, slots=True)
class SourceDetail:
    summary: SourceSummary
    source: CapturedSource
    deliveries: tuple[DeliverySummary, ...]
