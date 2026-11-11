"""Retained raw connection-request evidence; no effective state or participant grants."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.states import RequestState
from studymate.domain.time import require_aware

OPERATOR_REQUEST_PAGE_SIZE = 50
OPERATOR_REQUEST_SOURCE_BYTES = 32768
OPERATOR_REQUEST_ACKS_PER_REVISION = 2
MAX_OPERATOR_REQUEST_VERSION = (1 << 31) - 1


@dataclass(frozen=True, slots=True)
class OperatorRequestOrigin:
    """Raw recorded correlation, unlike stricter current audit/request transport validation."""

    http_request_id: UUID | None = None
    action_id: UUID | None = None
    trace_id: str | None = field(default=None, repr=False)
    span_id: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class OperatorRequestRoot:
    id: UUID
    relationship_id: UUID
    sender_id: UUID
    recipient_id: UUID
    preview_id: UUID
    mode: DiscoveryMode
    subject_id: UUID
    sent_at: datetime
    expires_at: datetime
    current_version: int
    state: RequestState
    origin: OperatorRequestOrigin

    def __post_init__(self) -> None:
        require_aware(self.sent_at)
        require_aware(self.expires_at)
        if (
            isinstance(self.current_version, bool)
            or not 1 <= self.current_version <= MAX_OPERATOR_REQUEST_VERSION
        ):
            raise ValueError("Request inspection requires its actual positive current version")

    def includes(self, account_id: UUID) -> bool:
        return account_id in (self.sender_id, self.recipient_id)


@dataclass(frozen=True, slots=True)
class OperatorRequestPreview:
    id: UUID
    sender_id: UUID
    recipient_id: UUID
    mode: DiscoveryMode
    subject_id: UUID
    created_at: datetime
    source_json_raw: str = field(repr=False)
    sender_goal_id: UUID | None
    sender_goal_version: int | None
    recipient_goal_id: UUID | None
    recipient_goal_version: int | None
    sender_help_version: int | None
    recipient_help_version: int | None

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        if not 1 <= len(self.source_json_raw.encode("utf-8")) <= OPERATOR_REQUEST_SOURCE_BYTES:
            raise ValueError("Request inspection exceeds its actual stored preview bound")


@dataclass(frozen=True, slots=True)
class OperatorRequestSnapshot:
    root: OperatorRequestRoot
    request_text: str = field(repr=False)
    note: str | None = field(repr=False)
    preview: OperatorRequestPreview = field(repr=False)

    def __post_init__(self) -> None:
        if (
            self.root.preview_id,
            self.root.sender_id,
            self.root.recipient_id,
            self.root.mode,
            self.root.subject_id,
        ) != (
            self.preview.id,
            self.preview.sender_id,
            self.preview.recipient_id,
            self.preview.mode,
            self.preview.subject_id,
        ):
            raise ValueError("Request snapshot differs from its actual owned preview source")


@dataclass(frozen=True, slots=True)
class OperatorRequestRevision:
    request_id: UUID
    version: int
    state: RequestState
    changed_at: datetime
    decline_until: datetime | None
    conversation_id: UUID | None

    def __post_init__(self) -> None:
        require_aware(self.changed_at)
        if self.decline_until is not None:
            require_aware(self.decline_until)
        if isinstance(self.version, bool) or not 1 <= self.version <= MAX_OPERATOR_REQUEST_VERSION:
            raise ValueError("Request inspection requires an actual positive stored revision")


@dataclass(frozen=True, slots=True)
class OperatorRequestDisclosure:
    id: UUID
    viewer_id: UUID
    request_id: UUID
    stored_version: int
    created_at: datetime
    origin: OperatorRequestOrigin

    def __post_init__(self) -> None:
        require_aware(self.created_at)


@dataclass(frozen=True, slots=True)
class OperatorRequestAcknowledgement:
    id: UUID
    viewer_id: UUID
    request_id: UUID
    stored_version: int
    acknowledged_at: datetime
    origin: OperatorRequestOrigin
    disclosure: OperatorRequestDisclosure

    def __post_init__(self) -> None:
        require_aware(self.acknowledged_at)
        if (self.viewer_id, self.request_id, self.stored_version) != (
            self.disclosure.viewer_id,
            self.disclosure.request_id,
            self.disclosure.stored_version,
        ):
            raise ValueError("Request ACK differs from its exact linked disclosure source")
