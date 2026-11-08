"""Safe invalidation hints: transport order is not business truth or a read receipt."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.time import require_aware

MAX_DELIVERY_SEQUENCE = (1 << 63) - 1
CHANGE_PAGE_SIZE = 50


class ChangeResource(StrEnum):
    ACCOUNT = "account"
    REQUEST = "request"
    CONVERSATION = "conversation"
    AI_JOB = "ai_job"


@dataclass(frozen=True, slots=True)
class ChangeHint:
    canonical_event_id: UUID
    recipient_id: UUID
    resource_type: ChangeResource
    resource_id: UUID
    version: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.resource_type, ChangeResource):
            raise ValueError("Change hint resource must be explicitly allowlisted")
        if self.version is not None and (
            isinstance(self.version, bool) or not 1 <= self.version <= MAX_DELIVERY_SEQUENCE
        ):
            raise ValueError("Change hint requires an actual bounded source version")


@dataclass(frozen=True, slots=True)
class PublishedChange:
    hint: ChangeHint
    sequence: int
    published_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.published_at)
        if isinstance(self.sequence, bool) or not 1 <= self.sequence <= MAX_DELIVERY_SEQUENCE:
            raise ValueError("Delivery sequence must be a positive recipient-owned integer")


@dataclass(frozen=True, slots=True)
class ChangeWindow:
    """Source snapshot after committed publication, before expiry beyond this floor."""

    recipient_id: UUID
    head_sequence: int
    expired_through_sequence: int
    changes: tuple[PublishedChange, ...]

    def __post_init__(self) -> None:
        for value in (self.head_sequence, self.expired_through_sequence):
            if isinstance(value, bool) or not 0 <= value <= MAX_DELIVERY_SEQUENCE:
                raise ValueError("Change stream head and expiry floor require bounded integers")
        if self.expired_through_sequence > self.head_sequence:
            raise ValueError("Transport expiry cannot move beyond its actual published head")
        if len(self.changes) > CHANGE_PAGE_SIZE + 1:
            raise ValueError("Change source exceeds its bounded lookahead")
        previous: int | None = None
        for change in self.changes:
            if (
                change.hint.recipient_id != self.recipient_id
                or not self.expired_through_sequence < change.sequence <= self.head_sequence
                or (previous is not None and change.sequence != previous + 1)
            ):
                raise ValueError("Change source lost its contiguous retained recipient scope")
            previous = change.sequence
