"""Read-only retained AI sources and bounded account-scoped metadata cursors."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.ai.jobs import JobState
from studymate.domain.ai.tasks import AiKind
from studymate.domain.operator.ai_jobs import OperatorAiJobDetail, OperatorAiJobMetadata
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorAiFilters:
    kind: AiKind | None = None
    state: JobState | None = None
    created_from: datetime | None = None
    created_before: datetime | None = None

    def __post_init__(self) -> None:
        for value in (self.created_from, self.created_before):
            if value is not None:
                require_aware(value)
        if (
            self.created_from is not None
            and self.created_before is not None
            and self.created_from >= self.created_before
        ):
            raise ValueError("AI inspection requires a nonempty half-open created interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.ai-jobs.v1",
            self.kind.value if self.kind is not None else "",
            self.state.value if self.state is not None else "",
            self.created_from.astimezone(UTC).isoformat() if self.created_from is not None else "",
            self.created_before.astimezone(UTC).isoformat()
            if self.created_before is not None
            else "",
        )

    def matches(self, row: OperatorAiJobMetadata) -> bool:
        return not (
            (self.kind is not None and row.kind != self.kind)
            or (self.state is not None and row.state != self.state)
            or (self.created_from is not None and row.created_at < self.created_from)
            or (self.created_before is not None and row.created_at >= self.created_before)
        )


@dataclass(frozen=True, slots=True)
class OperatorAiPosition:
    anchor_created_at: datetime
    anchor_job_id: UUID
    before_created_at: datetime
    before_job_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_created_at)
        require_aware(self.before_created_at)
        if (self.before_created_at, self.before_job_id.int) > (
            self.anchor_created_at,
            self.anchor_job_id.int,
        ):
            raise ValueError("AI inspection position exceeds its actual metadata anchor")


class OperatorAiCursorCodec(Protocol):
    def encode(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        fingerprint: bytes,
        position: OperatorAiPosition,
    ) -> str: ...
    def decode(
        self, scope: OperatorCursorScope, account_id: UUID, fingerprint: bytes, token: str
    ) -> OperatorAiPosition: ...


class OperatorAiTransaction(OperatorAuditTransaction, Protocol):
    async def ai_account(self, account_id: UUID) -> UUID | None: ...
    async def ai_jobs(
        self, account_id: UUID, filters: OperatorAiFilters, position: OperatorAiPosition | None
    ) -> tuple[OperatorAiJobMetadata, ...]:
        """At most51 metadata-only rows; never input/result/digest/lease/token/intent selection."""
        ...

    async def ai_job(self, account_id: UUID, job_id: UUID) -> OperatorAiJobDetail | None:
        """Exact owned raw business record and <=3 actual attempts; no task decoder."""
        ...


class OperatorAiUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorAiTransaction]: ...
