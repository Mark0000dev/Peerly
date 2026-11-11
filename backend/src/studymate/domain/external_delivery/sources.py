"""Closed selected sources. No private content, response bodies or credentials."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.client_observations.events import Observation
from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.operator.timeline import OperatorEventFacts, OperatorEventKind
from studymate.domain.support.cases import SupportTopic
from studymate.domain.time import require_aware


class Sink(StrEnum):
    UMAMI = "umami"
    TELEGRAM_SUPPORT = "telegram_support"


class SourceKind(StrEnum):
    CANONICAL = "canonical"
    CLIENT_OBSERVATION = "client_observation"
    SUPPORT_CASE = "support_case"


class CaptureMode(StrEnum):
    LIVE = "live"
    BACKFILL_UMAMI = "backfill_umami"


class MembershipEvidence(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    OTP = "otp"
    MANUAL_PLACEHOLDER = "manual_placeholder"
    MANUAL_CHALLENGE = "manual_challenge"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CanonicalSource:
    id: UUID
    actor_id: UUID
    kind: OperatorEventKind
    occurred_at: datetime
    facts: OperatorEventFacts
    membership_evidence: MembershipEvidence = MembershipEvidence.NOT_APPLICABLE
    notification_mode: NotificationMode | None = None

    def __post_init__(self) -> None:
        require_aware(self.occurred_at)
        if (self.kind == OperatorEventKind.EMAIL_CONFIRMED) != (
            self.membership_evidence != MembershipEvidence.NOT_APPLICABLE
        ):
            raise ValueError("Membership analytics requires explicit actual confirmation evidence")


@dataclass(frozen=True, slots=True)
class ClientObservationSource:
    id: UUID
    actor_id: UUID
    received_at: datetime
    event: Observation
    release_id: str | None

    def __post_init__(self) -> None:
        require_aware(self.received_at)


@dataclass(frozen=True, slots=True)
class SupportCaseSource:
    id: UUID
    actor_id: UUID | None
    topic: SupportTopic
    received_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.received_at)


type SelectedSource = CanonicalSource | ClientObservationSource | SupportCaseSource


@dataclass(frozen=True, slots=True)
class CapturedSource:
    id: UUID
    kind: SourceKind
    source: SelectedSource
    mode: CaptureMode
    captured_at: datetime
    routing_version: int = 1

    def __post_init__(self) -> None:
        require_aware(self.captured_at)
        if self.routing_version != 1 or isinstance(self.routing_version, bool):
            raise ValueError("Unsupported external delivery source routing version")
        actual_kind = {
            CanonicalSource: SourceKind.CANONICAL,
            ClientObservationSource: SourceKind.CLIENT_OBSERVATION,
            SupportCaseSource: SourceKind.SUPPORT_CASE,
        }[type(self.source)]
        if self.kind != actual_kind:
            raise ValueError("External delivery source lost its actual finite source family")
