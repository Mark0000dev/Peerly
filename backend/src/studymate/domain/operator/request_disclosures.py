"""Retained technical disclosure facts; neither an ACK nor proof of human attention."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from studymate.domain.operator.connection_requests import (
    MAX_OPERATOR_REQUEST_VERSION,
    OperatorRequestDisclosure,
    OperatorRequestOrigin,
)
from studymate.domain.time import require_aware

OPERATOR_DISCLOSURE_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class OperatorRetainedDisclosure:
    id: UUID
    viewer_id: UUID
    request_id: UUID
    stored_version: int
    sender_id: UUID
    recipient_id: UUID
    created_at: datetime
    origin: OperatorRequestOrigin

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        if (
            isinstance(self.stored_version, bool)
            or not 1 <= self.stored_version <= MAX_OPERATOR_REQUEST_VERSION
            or self.sender_id == self.recipient_id
            or self.viewer_id not in (self.sender_id, self.recipient_id)
        ):
            raise ValueError("Disclosure requires its actual participant and stored version")

    def linked_source(self) -> OperatorRequestDisclosure:
        return OperatorRequestDisclosure(
            self.id,
            self.viewer_id,
            self.request_id,
            self.stored_version,
            self.created_at,
            self.origin,
        )
