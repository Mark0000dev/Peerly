from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from studymate.application.ai.ports import Admission, AiQuotaError, AiUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.operator.authority import OperatorPrincipal
from studymate.application.operator.report_triage_ports import (
    PreparedReportTriageSource,
    ReportTriageAdmission,
    StoredReportTriage,
    TriageAuthorityFacts,
    TriageIntentObservation,
)
from studymate.domain.ai.jobs import AiJob, Failure, Versions
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.profile_reports import OperatorReportKind
from studymate.domain.operator.report_triage import (
    ReportTriageEvidenceContext,
    ReportTriageEvidenceSnapshot,
    ReportTriageSourcePreview,
    ReportTriageSubmission,
)
from studymate.domain.report_moderation.reviews import ReviewReportSource
from tests.unit.operator.store import TARGET, Store

REPORT_ID = UUID(int=8101)
VERSIONS = Versions("controlled-triage-model")


class TriageStore(Store):
    def __init__(self) -> None:
        super().__init__()
        report = ReviewReportSource(
            REPORT_ID, OperatorReportKind.PROFILE, UUID(int=8102), TARGET, UUID(int=8103)
        )
        self.preview: ReportTriageSourcePreview | None = ReportTriageSourcePreview(
            report, ReportTriageEvidenceContext(report, None, "Exact private selected evidence")
        )
        self.snapshots: list[ReportTriageEvidenceSnapshot] = []
        self.jobs: dict[UUID, AiJob] = {}
        self.proofs: dict[UUID, ReportTriageSubmission] = {}
        self.intents: dict[tuple[UUID, str], tuple[bytes, UUID]] = {}
        self.events: list[UUID] = []
        self.queue_full = False
        self.quota = False
        self.fail_canonical = False
        self.expire_after_admit = False
        self.fail_commit = False

    @asynccontextmanager
    async def transaction(
        self, actor_secret_digest: bytes | None = None, report_id: UUID | None = None
    ) -> AsyncIterator["TriageStore"]:
        if actor_secret_digest is not None:
            assert actor_secret_digest
            assert report_id is not None
        before = (
            self.snapshots.copy(),
            self.jobs.copy(),
            self.proofs.copy(),
            self.intents.copy(),
            self.events.copy(),
        )
        try:
            async with super().transaction():
                yield self
                if self.fail_commit:
                    raise RuntimeError("synthetic triage commit failure")
        except BaseException:
            self.snapshots, self.jobs, self.proofs, self.intents, self.events = before
            raise

    async def lock_triage_authority(self, digest: bytes) -> TriageAuthorityFacts:
        identity = await self.lock_identity(digest)
        access = (
            await self.operator_access(identity.session.account_id)
            if identity is not None
            else None
        )
        return TriageAuthorityFacts(identity, access, await self.now())

    def bind_triage_operator(self, principal: OperatorPrincipal) -> None:
        assert principal.identity == self.actor
        assert principal.access == self.access

    async def lock_triage_context(self, report_id: UUID) -> ReportTriageSourcePreview | None:
        self.queried()
        return (
            self.preview
            if self.preview is not None and self.preview.report.id == report_id
            else None
        )

    def stored(self, job_id: UUID) -> StoredReportTriage:
        job = self.jobs[job_id]
        snapshot = next(
            row
            for row in self.snapshots
            if row.report.id == job.task.source.id and row.version == job.task.source.version
        )
        return StoredReportTriage(job, snapshot, self.proofs[job_id])

    async def replay_triage(
        self, actor_id: UUID, key: IntentKey, digest: bytes
    ) -> TriageIntentObservation:
        value = self.intents.get((actor_id, key.value))
        if value is None:
            return TriageIntentObservation(None, self.clock)
        previous, job_id = value
        if previous != digest:
            raise IdempotencyConflictError
        return TriageIntentObservation(self.stored(job_id), self.clock)

    async def prepare_triage_source(
        self,
        context: ReportTriageEvidenceContext,
        access: OperatorAccess,
        actor_session_id: UUID,
        at: datetime,
    ) -> PreparedReportTriageSource:
        for previous in self.snapshots:
            if (
                previous.report == context.report
                and previous.operator == access
                and previous.actor_session_id == actor_session_id
                and previous.review_version == context.review_version
                and previous.evidence_digest == context.evidence_digest
            ):
                return PreparedReportTriageSource(previous, True)
        previous_version = self.snapshots[-1].version if self.snapshots else None
        snapshot = ReportTriageEvidenceSnapshot(
            context.report,
            previous_version + 1 if previous_version is not None else 1,
            previous_version,
            context.review_version,
            access,
            actor_session_id,
            context.evidence,
            context.evidence_digest,
            at,
        )
        return PreparedReportTriageSource(snapshot, False)

    async def admit_triage_submission(self, request: ReportTriageAdmission) -> StoredReportTriage:
        snapshot = request.source.snapshot
        if not request.source.exists:
            self.snapshots.append(snapshot)
        job = await self.admit_triage(
            Admission(
                snapshot.operator.account_id,
                snapshot.task,
                request.key,
                request.digest,
                await self.runtime_versions(self.clock),
            ),
            self.clock,
        )
        proof = await self.record_triage_submission(snapshot, job, request.event_id)
        return StoredReportTriage(job, snapshot, proof)

    async def runtime_versions(self, at: datetime) -> Versions:
        assert at == self.clock
        return VERSIONS

    async def admit_triage(self, intent: Admission, at: datetime) -> AiJob:
        if self.queue_full:
            raise AiUnavailableError
        if self.quota:
            raise AiQuotaError
        job = AiJob(
            uuid4(),
            intent.actor_id,
            intent.task,
            intent.digest,
            intent.versions,
            at,
            at + timedelta(minutes=30),
            at,
        )
        self.jobs[job.id] = job
        self.intents[(intent.actor_id, intent.key.value)] = (intent.digest, job.id)
        if self.expire_after_admit:
            self.clock = self.actor.session.expires_at
        return job

    async def record_triage_submission(
        self, snapshot: ReportTriageEvidenceSnapshot, job: AiJob, event_id: UUID
    ) -> ReportTriageSubmission:
        proof = ReportTriageSubmission(
            job.id,
            snapshot.report.id,
            snapshot.version,
            snapshot.operator,
            snapshot.actor_session_id,
            job.created_at,
            event_id,
        )
        self.proofs[job.id] = proof
        self.events.append(event_id)
        if self.fail_canonical:
            raise RuntimeError("synthetic triage canonical failure")
        return proof

    async def latest_triage(self, report_id: UUID) -> StoredReportTriage | None:
        matching = tuple(row for row in self.proofs.values() if row.report_id == report_id)
        return self.stored(matching[-1].job_id) if matching else None

    async def triage_source_failure(self, stored: StoredReportTriage) -> Failure | None:
        current = self.preview.context if self.preview is not None else None
        if stored.snapshot.operator != self.access:
            return Failure.ACCOUNT
        if current is None or (current.report, current.review_version, current.evidence_digest) != (
            stored.snapshot.report,
            stored.snapshot.review_version,
            stored.snapshot.evidence_digest,
        ):
            return Failure.STALE_SOURCE
        return None

    def change_evidence(self) -> None:
        assert self.preview is not None
        assert self.preview.context is not None
        self.preview = replace(
            self.preview,
            context=replace(self.preview.context, evidence="Actually changed selected evidence"),
        )
