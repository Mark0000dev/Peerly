from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.report_moderation.reviews import ReportReviewRevision, ReviewReportSource


@dataclass(frozen=True, slots=True)
class ReportReviewIntent:
    fingerprint: bytes = field(repr=False)
    result: ReportReviewRevision


class ReportModerationTransaction(OperatorAuditTransaction, Protocol):
    async def lock_report(self, report_id: UUID) -> ReviewReportSource | None: ...
    async def latest_review(self, report_id: UUID) -> ReportReviewRevision | None: ...
    async def prior_review(self, actor_id: UUID, key: IntentKey) -> ReportReviewIntent | None: ...
    async def append_review(
        self, source: ReportReviewRevision, key: IntentKey, fingerprint: bytes
    ) -> ReportReviewRevision:
        """Atomically persist immutable decision, canonical mutation event and original receipt."""
        ...

    async def review_history(
        self, report_id: UUID, anchor: int, before: int | None
    ) -> tuple[ReportReviewRevision, ...]: ...


class ReportModerationUnitOfWork(Protocol):
    def transaction(
        self, actor_secret_digest: bytes, report_id: UUID
    ) -> AbstractAsyncContextManager[ReportModerationTransaction]: ...
