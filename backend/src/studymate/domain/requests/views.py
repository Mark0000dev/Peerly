"""Technical detail disclosure and explicit observation receipt, never a profile grant."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class RequestDisclosure:
    id: UUID
    viewer_id: UUID
    request_id: UUID
    stored_version: int
    created_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.created_at)
        if isinstance(self.stored_version, bool) or self.stored_version < 1:
            raise ValueError("Disclosure needs an actual positive stored request revision")


@dataclass(frozen=True, slots=True)
class RequestViewReceipt:
    id: UUID
    viewer_id: UUID
    request_id: UUID
    stored_version: int
    disclosure_id: UUID
    acknowledged_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.acknowledged_at)
        if isinstance(self.stored_version, bool) or self.stored_version < 1:
            raise ValueError("View acknowledgement needs an actual stored request revision")
