from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.ai.ports import Admission
from studymate.application.idempotency import IntentKey
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.ai.jobs import AiJob, Failure, Versions
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.report_triage import (
    ReportTriageEvidenceContext,
    ReportTriageEvidenceSnapshot,
    ReportTriageSourceClaims,
    ReportTriageSourcePreview,
    ReportTriageSubmission,
)


class InvalidReportTriageSourceError(Exception):
    pass


class ReportTriageSourceUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class StoredReportTriage:
    job: AiJob = field(repr=False)
    snapshot: ReportTriageEvidenceSnapshot = field(repr=False)
    submission: ReportTriageSubmission


class ReportTriageSourceCodec(Protocol):
    def encode_source(self, claims: ReportTriageSourceClaims) -> str: ...
    def decode_source(
        self,
        token: str,
        access: OperatorAccess,
        actor_session_id: UUID,
        report_id: UUID,
        now: datetime,
    ) -> ReportTriageSourceClaims: ...


class OperatorReportTriageTransaction(OperatorAuditTransaction, Protocol):
    async def lock_triage_context(self, report_id: UUID) -> ReportTriageSourcePreview | None: ...
    async def replay_triage(
        self, actor_id: UUID, key: IntentKey, digest: bytes
    ) -> StoredReportTriage | None: ...
    async def materialize_triage_source(
        self,
        context: ReportTriageEvidenceContext,
        access: OperatorAccess,
        actor_session_id: UUID,
        at: datetime,
    ) -> ReportTriageEvidenceSnapshot: ...
    async def runtime_versions(self, at: datetime) -> Versions: ...
    async def admit_triage(self, intent: Admission, at: datetime) -> AiJob: ...
    async def record_triage_submission(
        self, snapshot: ReportTriageEvidenceSnapshot, job: AiJob, event_id: UUID
    ) -> ReportTriageSubmission: ...
    async def latest_triage(self, report_id: UUID) -> StoredReportTriage | None: ...
    async def triage_source_failure(self, stored: StoredReportTriage) -> Failure | None: ...


class OperatorReportTriageUnitOfWork(Protocol):
    def transaction(
        self, actor_secret_digest: bytes, report_id: UUID
    ) -> AbstractAsyncContextManager[OperatorReportTriageTransaction]: ...
