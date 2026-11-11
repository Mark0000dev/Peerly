from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.external_delivery.sources import (
    CapturedSource,
    Sink,
    SupportCaseSource,
)
from studymate.domain.time import require_aware

MAX_RETRY_METADATA_SECONDS = (1 << 31) - 1
MAX_PROVIDER_MESSAGE_ID = (1 << 63) - 1
MIN_HTTP_STATUS = 100
MAX_HTTP_STATUS = 599
MAX_ATTEMPTS = 8
PROJECTION_VERSION = 1


class FailureCode(StrEnum):
    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    CREDENTIALS = "credentials_unavailable"
    DESTINATION = "destination_unavailable"
    INVALID_RESPONSE = "invalid_response"
    TIMEOUT = "timeout"
    LEASE_EXPIRED = "lease_expired"
    CANCELLED = "cancelled"
    PERMANENT = "permanent"


class ResultKind(StrEnum):
    ACCEPTED = "accepted"
    RETRYABLE = "retryable"
    AMBIGUOUS = "ambiguous"
    PERMANENT = "permanent"


class DeliveryState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RETRY = "retry"
    SUCCEEDED = "succeeded"
    DEAD = "dead"


@dataclass(frozen=True, slots=True)
class DestinationRef:
    sink: Sink
    revision: int

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("External delivery requires an actual registered destination revision")


@dataclass(frozen=True, slots=True)
class UmamiEvent:
    source: CapturedSource


@dataclass(frozen=True, slots=True)
class SupportTelegramNotice:
    source: SupportCaseSource


type DeliveryPayload = UmamiEvent | SupportTelegramNotice


@dataclass(frozen=True, slots=True)
class DeliveryLease:
    delivery_id: UUID
    source_id: UUID
    destination: DestinationRef
    lease_id: UUID
    attempt_no: int
    started_at: datetime
    lease_until: datetime
    payload: DeliveryPayload
    projection_version: int = PROJECTION_VERSION

    def __post_init__(self) -> None:
        require_aware(self.started_at)
        require_aware(self.lease_until)
        if (
            isinstance(self.attempt_no, bool)
            or not 1 <= self.attempt_no <= MAX_ATTEMPTS
            or self.lease_until <= self.started_at
            or self.projection_version != PROJECTION_VERSION
        ):
            raise ValueError("External delivery lease requires its actual bounded source attempt")
        expected = {
            UmamiEvent: Sink.UMAMI,
            SupportTelegramNotice: Sink.TELEGRAM_SUPPORT,
        }[type(self.payload)]
        if self.destination.sink != expected:
            raise ValueError("External delivery lease cannot rebind its payload to another sink")


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    kind: ResultKind
    failure: FailureCode | None = None
    http_status: int | None = None
    retry_after_seconds: int | None = None
    provider_message_id: int | None = None

    def __post_init__(self) -> None:
        if (self.kind == ResultKind.ACCEPTED) != (self.failure is None):
            raise ValueError(
                "External delivery outcome must retain its actual failure classification"
            )
        if self.http_status is not None and (
            isinstance(self.http_status, bool)
            or not MIN_HTTP_STATUS <= self.http_status <= MAX_HTTP_STATUS
        ):
            raise ValueError("External delivery HTTP status is outside its finite bounds")
        if self.retry_after_seconds is not None and (
            isinstance(self.retry_after_seconds, bool)
            or not 1 <= self.retry_after_seconds <= MAX_RETRY_METADATA_SECONDS
        ):
            raise ValueError("Provider retry instructions require positive seconds")
        if self.provider_message_id is not None and (
            isinstance(self.provider_message_id, bool)
            or not 1 <= self.provider_message_id <= MAX_PROVIDER_MESSAGE_ID
        ):
            raise ValueError("Provider message receipt requires its actual positive identifier")
