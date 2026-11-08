"""Two short authorization/audit transactions; no connection held for object I/O."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import OperatorAuditOutcome
from studymate.domain.operator.profile_media import (
    OperatorProfileMediaRequest,
    OperatorProfileMediaSource,
)
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorProfileMediaAudit:
    """Typed canonical audit input; persisted through the existing operator journal."""

    id: UUID
    access: OperatorAccess
    request: OperatorProfileMediaRequest
    at: datetime
    outcome: OperatorAuditOutcome
    actual_source_upload_id: UUID | None

    def __post_init__(self) -> None:
        require_aware(self.at)
        if not self.access.is_active(self.at):
            raise ValueError("Media inspection requires its actual active operator revision")
        if self.outcome not in (OperatorAuditOutcome.READ, OperatorAuditOutcome.NOT_FOUND):
            raise ValueError("Media inspection requires an actual read/not-found outcome")
        if self.actual_source_upload_id not in (None, self.request.upload_id) or (
            self.outcome == OperatorAuditOutcome.READ and self.actual_source_upload_id is None
        ):
            raise ValueError("Media inspection cannot invent a known returned upload source")


class OperatorProfileMediaTransaction(OperatorAuditTransaction, Protocol):
    async def profile_media_source(
        self,
        request: OperatorProfileMediaRequest,
    ) -> OperatorProfileMediaSource | None:
        """Exact retained upload-owner and attempt source, regardless of lifecycle/READY state."""
        ...

    async def save_profile_media_audit(self, inspection: OperatorProfileMediaAudit) -> None:
        """Actual canonical operator audit in this transaction; no content or parallel journal."""
        ...


class OperatorProfileMediaUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorProfileMediaTransaction]: ...
