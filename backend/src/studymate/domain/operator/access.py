from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorAccess:
    """A retained explicitly assigned DB revision, not provider/email-derived privilege."""

    account_id: UUID
    version: int
    active: bool
    changed_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.changed_at)
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Operator access needs an actual positive revision")
        if not isinstance(self.active, bool):
            raise ValueError("Operator assignment requires an explicit boolean state")

    def is_active(self, at: datetime) -> bool:
        require_aware(at)
        return self.active and self.changed_at <= at
