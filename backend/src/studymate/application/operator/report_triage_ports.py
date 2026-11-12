from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.operator.authority import OperatorPrincipal
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.ai.jobs import AiJob, Failure
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


@dataclass(frozen=True, slots=True)
class PreparedReportTriageSource:
    snapshot: ReportTriageEvidenceSnapshot = field(repr=False)
    exists: bool


@dataclass(frozen=True, slots=True)
class ReportTriageAdmission:
    source: PreparedReportTriageSource = field(repr=False)
    key: IntentKey
    digest: bytes = field(repr=False)
    event_id: UUID


@dataclass(frozen=True, slots=True)
class TriageAuthorityFacts:
    identity: IdentitySnapshot | None = field(repr=False)
    access: OperatorAccess | None
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class TriageIntentObservation:
    stored: StoredReportTriage | None = field(repr=False)
    observed_at: datetime


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
    async def lock_triage_authority(self, digest: bytes) -> TriageAuthorityFacts: ...
    def bind_triage_operator(self, principal: OperatorPrincipal) -> None: ...
    async def lock_triage_context(self, report_id: UUID) -> ReportTriageSourcePreview | None: ...
    async def replay_triage(
        self, actor_id: UUID, key: IntentKey, digest: bytes
    ) -> TriageIntentObservation: ...
    async def prepare_triage_source(
        self,
        context: ReportTriageEvidenceContext,
        access: OperatorAccess,
        actor_session_id: UUID,
        at: datetime,
    ) -> PreparedReportTriageSource: ...
    async def admit_triage_submission(
        self, request: ReportTriageAdmission
    ) -> StoredReportTriage: ...
    async def latest_triage(self, report_id: UUID) -> StoredReportTriage | None: ...
    async def triage_source_failure(self, stored: StoredReportTriage) -> Failure | None: ...


class OperatorReportTriageUnitOfWork(Protocol):
    def transaction(
        self, actor_secret_digest: bytes, report_id: UUID
    ) -> AbstractAsyncContextManager[OperatorReportTriageTransaction]: ...
