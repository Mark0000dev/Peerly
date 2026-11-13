"""Retained verification requests and safe delivery metadata, never delivery promises."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

EMAIL_HISTORY_PAGE_SIZE = 50


class StoredEmailDeliveryStatus(StrEnum):
    QUEUED = "queued"
    INFLIGHT = "inflight"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StoredEmailDeliveryError(StrEnum):
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_REJECTED = "provider_rejected"
    ENVELOPE_INVALID = "envelope_invalid"
    DELIVERY_EXPIRED = "delivery_expired"


@dataclass(frozen=True, slots=True)
class EmailHistoryDelivery:
    id: UUID
    status: StoredEmailDeliveryStatus
    created_at: datetime
    due_at: datetime
    attempts: int
    delivered_at: datetime | None
    last_error: StoredEmailDeliveryError | None
    origin_request_id: UUID | None
    origin_action_id: UUID | None
    origin_trace_id: str | None
    origin_span_id: str | None


@dataclass(frozen=True, slots=True)
class EmailHistoryManualVerification:
    id: UUID
    operator_id: UUID
    operator_access_version: int
    event_id: UUID
    verified_at: datetime


@dataclass(frozen=True, slots=True)
class EmailHistoryChallenge:
    id: UUID
    account_id: UUID
    session_id: UUID
    email: str = field(repr=False)
    created_at: datetime
    expires_at: datetime
    resend_at: datetime
    attempts: int
    consumed_at: datetime | None
    superseded_at: datetime | None
    delivery: EmailHistoryDelivery | None
    manual_verification: EmailHistoryManualVerification | None
