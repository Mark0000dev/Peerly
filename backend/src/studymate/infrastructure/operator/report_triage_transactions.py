"""Operator-authorized report snapshots reuse the actual bounded AI admission transaction."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.ai.policy import AdmissionPolicy
from studymate.application.ai.ports import Admission, AiUnavailableError
from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.operator.report_triage_ports import (
    ReportTriageSourceUnavailableError,
    StoredReportTriage,
)
from studymate.domain.ai.jobs import AiJob, Failure, Versions
from studymate.domain.ai.tasks import AiKind, TriageReport
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.profile_reports import OperatorReportKind
from studymate.domain.operator.report_triage import (
    MAX_TRIAGE_SOURCE_VERSION,
    ReportTriageEvidenceContext,
    ReportTriageEvidenceSnapshot,
    ReportTriageSourcePreview,
    ReportTriageSubmission,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.infrastructure.ai.models import AiJobRecord
from studymate.infrastructure.ai.persistence import job_value
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.operator.models import OperatorAccessRevisionRecord
from studymate.infrastructure.operator.report_triage_admission import SqlOperatorTriageAdmission
from studymate.infrastructure.operator.report_triage_guard import SqlReportTriageSourceGuard
from studymate.infrastructure.operator.report_triage_models import (
    ReportTriageEvidenceRecord,
    ReportTriageSubmissionRecord,
)
from studymate.infrastructure.operator.report_triage_sources import selected_report_preview
from studymate.infrastructure.operator.report_triage_values import (
    triage_snapshot_value,
    triage_submission_value,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.report_moderation.transactions import report_source


class ReportTriageRecorder(Protocol):
    async def __call__(self, session: AsyncSession, source: ReportTriageSubmission) -> None: ...


@dataclass(slots=True)
class TriageIdentity:
    original: IdentitySnapshot | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlOperatorReportTriageTransaction(SqlOperatorTransaction):
    report_id: UUID
    target_id: UUID | None
    triage_recorder: ReportTriageRecorder
    policy: AdmissionPolicy = field(default_factory=AdmissionPolicy)
    identity: TriageIdentity = field(default_factory=TriageIdentity)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        actor = (
            await self.lock_identity_for_peer(secret_digest, self.target_id)
            if self.target_id is not None
            else await SqlIdentityTransaction.lock_identity(self, secret_digest)
        )
        self.identity.original = actor
        return actor

    def checked_triage_actor(self) -> OperatorAccess:
        access = self.checked_access()
        actor = self.identity.original
        if actor is None or actor.session.account_id != access.account_id:
            raise RuntimeError("Triage lacks its actual current operator/session authority")
        return access

    def checked_triage_session(self) -> IdentitySnapshot:
        self.checked_triage_actor()
        actor = self.identity.original
        if actor is None:
            raise RuntimeError("Triage lacks its actual authenticated actor session")
        return actor

    def internal_admission(self) -> SqlOperatorTriageAdmission:
        self.checked_triage_actor()
        return SqlOperatorTriageAdmission(self.session, self.policy, scope=self)

    async def lock_triage_context(self, report_id: UUID) -> ReportTriageSourcePreview | None:
        self.checked_triage_actor()
        if report_id != self.report_id:
            raise RuntimeError("Triage report differs from its ordered lock scope")
        source = await report_source(self.session, report_id, lock=True)
        if source is None:
            return None
        if source.target_id != self.target_id:
            raise RuntimeError("Triage target differs from its ordered account locks")
        return await selected_report_preview(self.session, source)

    async def stored_triage(self, job_id: UUID) -> StoredReportTriage:
        self.checked_triage_actor()
        proof = await self.session.get(ReportTriageSubmissionRecord, job_id)
        if proof is None or proof.report_id != self.report_id:
            raise RuntimeError("Triage job lacks its actual report submission proof")
        source, grant = (
            await self.session.execute(
                select(ReportTriageEvidenceRecord, OperatorAccessRevisionRecord)
                .join(
                    OperatorAccessRevisionRecord,
                    and_(
                        OperatorAccessRevisionRecord.account_id
                        == ReportTriageEvidenceRecord.operator_id,
                        OperatorAccessRevisionRecord.version
                        == ReportTriageEvidenceRecord.operator_access_version,
                    ),
                )
                .where(
                    ReportTriageEvidenceRecord.report_id == proof.report_id,
                    ReportTriageEvidenceRecord.version == proof.source_version,
                )
            )
        ).one()
        snapshot = triage_snapshot_value(source, grant)
        job = await self.session.get(AiJobRecord, job_id)
        if job is None or (job.actor_id, job.kind, job.source_id, job.source_version) != (
            proof.operator_id,
            "triage_report",
            proof.report_id,
            proof.source_version,
        ):
            raise RuntimeError("Triage submission differs from the actual AI job source/actor")
        return StoredReportTriage(
            job_value(job), snapshot, triage_submission_value(proof, snapshot)
        )

    async def replay_triage(
        self, actor_id: UUID, key: IntentKey, digest: bytes
    ) -> StoredReportTriage | None:
        job = await self.internal_admission().replay(actor_id, AiKind.TRIAGE_REPORT, key, digest)
        return await self.stored_triage(job.id) if job is not None else None

    async def materialize_triage_source(
        self,
        context: ReportTriageEvidenceContext,
        access: OperatorAccess,
        actor_session_id: UUID,
        at: datetime,
    ) -> ReportTriageEvidenceSnapshot:
        actor = self.checked_triage_session()
        if (
            context.report.id != self.report_id
            or context.report.target_id != self.target_id
            or access != self.checked_triage_actor()
            or actor_session_id != actor.session.id
        ):
            raise RuntimeError("Triage materialization differs from actual locked source/authority")
        existing = await self.session.scalar(
            select(ReportTriageEvidenceRecord)
            .where(
                ReportTriageEvidenceRecord.report_id == self.report_id,
                ReportTriageEvidenceRecord.operator_id == access.account_id,
                ReportTriageEvidenceRecord.operator_access_version == access.version,
                ReportTriageEvidenceRecord.actor_session_id == actor_session_id,
                ReportTriageEvidenceRecord.review_version.is_not_distinct_from(
                    context.review_version
                ),
                ReportTriageEvidenceRecord.evidence_digest == context.evidence_digest,
            )
            .order_by(ReportTriageEvidenceRecord.version.desc())
            .limit(1)
        )
        if existing is not None:
            original = await self.session.get(
                OperatorAccessRevisionRecord, (access.account_id, access.version)
            )
            if original is None:
                raise RuntimeError("Triage snapshot lost its original operator grant")
            return triage_snapshot_value(existing, original)
        previous = await self.session.scalar(
            select(func.max(ReportTriageEvidenceRecord.version)).where(
                ReportTriageEvidenceRecord.report_id == self.report_id
            )
        )
        if previous is not None and previous >= MAX_TRIAGE_SOURCE_VERSION:
            raise ReportTriageSourceUnavailableError
        version = previous + 1 if previous is not None else 1
        snapshot = ReportTriageEvidenceSnapshot(
            context.report,
            version,
            previous,
            context.review_version,
            access,
            actor_session_id,
            context.evidence,
            context.evidence_digest,
            at,
        )
        profile = context.report.kind == OperatorReportKind.PROFILE
        self.session.add(
            ReportTriageEvidenceRecord(
                report_id=self.report_id,
                version=version,
                previous_version=previous,
                review_version=context.review_version,
                report_kind=context.report.kind.value,
                reporter_id=context.report.reporter_id,
                target_id=context.report.target_id,
                profile_context_id=context.report.context_id if profile else None,
                message_context_id=None if profile else context.report.context_id,
                operator_id=access.account_id,
                operator_access_version=access.version,
                operator_access_active=access.active,
                actor_session_id=actor_session_id,
                evidence=context.evidence,
                evidence_digest=context.evidence_digest,
                captured_at=at,
            )
        )
        await self.session.flush()
        return snapshot

    async def runtime_versions(self, at: datetime) -> Versions:
        return await self.internal_admission().runtime_versions(at)

    async def admit_triage(self, intent: Admission, at: datetime) -> AiJob:
        if (
            intent.actor_id != self.checked_triage_actor().account_id
            or not isinstance(intent.task, TriageReport)
            or intent.task.source.id != self.report_id
        ):
            raise RuntimeError("Triage admission lacks its actual operator/report task")
        return await self.internal_admission().admit(intent, at)

    async def record_triage_submission(
        self, snapshot: ReportTriageEvidenceSnapshot, job: AiJob, event_id: UUID
    ) -> ReportTriageSubmission:
        actor = self.checked_triage_session()
        if (
            snapshot.operator != self.checked_triage_actor()
            or snapshot.actor_session_id != actor.session.id
            or snapshot.report.id != self.report_id
            or job.actor_id != snapshot.operator.account_id
            or job.task != snapshot.task
            or job.created_at < snapshot.captured_at
        ):
            raise RuntimeError("Triage submission differs from the actual admission/actor/source")
        existing = await self.session.get(ReportTriageSubmissionRecord, job.id)
        if existing is not None:
            return triage_submission_value(existing, snapshot)
        origin = current_origin()
        source = ReportTriageSubmission(
            job.id,
            self.report_id,
            snapshot.version,
            snapshot.operator,
            snapshot.actor_session_id,
            job.created_at,
            event_id,
            OperatorEventOrigin(
                origin.request_id, origin.action_id, origin.trace_id, origin.span_id
            )
            if origin is not None
            else OperatorEventOrigin(),
        )
        self.session.add(
            ReportTriageSubmissionRecord(
                job_id=job.id,
                report_id=source.report_id,
                source_version=source.source_version,
                operator_id=source.operator.account_id,
                operator_access_version=source.operator.version,
                operator_access_active=source.operator.active,
                actor_session_id=source.actor_session_id,
                kind="triage_report",
                submitted_at=source.submitted_at,
                event_id=source.event_id,
                event_kind="triage.submitted",
                http_request_id=source.origin.http_request_id,
                action_id=source.origin.action_id,
                trace_id=source.origin.trace_id,
                span_id=source.origin.span_id,
            )
        )
        await self.session.flush()
        await self.triage_recorder(self.session, source)
        return source

    async def latest_triage(self, report_id: UUID) -> StoredReportTriage | None:
        self.checked_triage_actor()
        if report_id != self.report_id:
            raise RuntimeError("Triage inspection differs from actual requested report")
        job_id = await self.session.scalar(
            select(ReportTriageSubmissionRecord.job_id)
            .where(ReportTriageSubmissionRecord.report_id == report_id)
            .order_by(
                ReportTriageSubmissionRecord.submitted_at.desc(),
                ReportTriageSubmissionRecord.job_id.desc(),
            )
            .limit(1)
        )
        return await self.stored_triage(job_id) if job_id is not None else None

    async def triage_source_failure(self, stored: StoredReportTriage) -> Failure | None:
        self.checked_triage_actor()
        # This is an advisory observation under current viewer authority. Worker
        # claim/finalization uses the default locking check in its OWN transaction.
        return await SqlReportTriageSourceGuard().check(self.session, stored.job, lock=False)


@dataclass(frozen=True, slots=True)
class SqlOperatorReportTriageUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder
    triage_recorder: ReportTriageRecorder
    policy: AdmissionPolicy = field(default_factory=AdmissionPolicy)

    @asynccontextmanager
    async def transaction(
        self, actor_secret_digest: bytes, report_id: UUID
    ) -> AsyncIterator[SqlOperatorReportTriageTransaction]:
        try:
            async with asyncio.timeout(self.policy.request_budget_seconds):
                async with open_transaction(self.sessions) as session:
                    source = await report_source(session, report_id)
                    target_id = source.target_id if source is not None else None
                    identity = SqlIdentityTransaction(session)
                    if target_id is not None:
                        await identity.lock_identity_for_peer(actor_secret_digest, target_id)
                    else:
                        await identity.lock_identity(actor_secret_digest)
                    yield SqlOperatorReportTriageTransaction(
                        session,
                        self.recorder,
                        report_id=report_id,
                        target_id=target_id,
                        triage_recorder=self.triage_recorder,
                        policy=self.policy,
                    )
        except (StorageUnavailableError, TimeoutError):
            raise AiUnavailableError from None
