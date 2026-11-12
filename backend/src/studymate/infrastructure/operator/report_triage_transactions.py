"""Operator-authorized report snapshots reuse the actual bounded AI admission transaction."""

import asyncio
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, func, literal, select, true
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from studymate.application.ai.policy import AdmissionPolicy
from studymate.application.ai.ports import AiUnavailableError
from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.operator.authority import OperatorPrincipal
from studymate.application.operator.report_triage_ports import (
    PreparedReportTriageSource,
    ReportTriageAdmission,
    ReportTriageSourceUnavailableError,
    StoredReportTriage,
    TriageAuthorityFacts,
    TriageIntentObservation,
)
from studymate.domain.ai.jobs import Failure
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.report_triage import (
    MAX_TRIAGE_SOURCE_VERSION,
    ReportTriageEvidenceContext,
    ReportTriageEvidenceSnapshot,
    ReportTriageSourcePreview,
    ReportTriageSubmission,
)
from studymate.domain.report_moderation.reviews import ReviewReportSource
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
)
from studymate.infrastructure.operator.report_triage_admission import admit_triage_submission
from studymate.infrastructure.operator.report_triage_guard import SqlReportTriageSourceGuard
from studymate.infrastructure.operator.report_triage_identity import lock_triage_identity
from studymate.infrastructure.operator.report_triage_models import (
    ReportTriageEvidenceRecord,
)
from studymate.infrastructure.operator.report_triage_reads import (
    read_latest_triage,
    read_triage_intent,
    read_triage_job,
)
from studymate.infrastructure.operator.report_triage_sources import selected_locked_report_preview
from studymate.infrastructure.operator.report_triage_values import (
    triage_snapshot_value,
)
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import ExternalIdentityRecord
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.report_moderation.transactions import report_source


class ReportTriageRecorder(Protocol):
    async def __call__(self, session: AsyncSession, source: ReportTriageSubmission) -> None: ...


@dataclass(slots=True)
class TriageIdentity:
    original: IdentitySnapshot | None = None
    facts: TriageAuthorityFacts | None = None
    bound: OperatorPrincipal | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlOperatorReportTriageTransaction(SqlOperatorTransaction):
    report_id: UUID
    target_id: UUID | None
    expected_source: ReviewReportSource | None = field(repr=False)
    actor_secret_digest: bytes = field(repr=False)
    triage_recorder: ReportTriageRecorder
    policy: AdmissionPolicy = field(default_factory=AdmissionPolicy)
    identity: TriageIdentity = field(default_factory=TriageIdentity)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        if not hmac.compare_digest(secret_digest, self.actor_secret_digest):
            raise RuntimeError("Triage identity differs from its actual scoped actor")
        actor = await lock_triage_identity(self.session, secret_digest, self.target_id)
        self.identity.original = actor
        return actor

    async def lock_triage_authority(self, digest: bytes) -> TriageAuthorityFacts:
        identity = await self.lock_identity(digest)
        access = None
        if identity is not None:
            actor_id = identity.session.account_id
            row = await self.session.scalar(
                select(OperatorAccessRevisionRecord)
                .join(
                    OperatorAccessRecord,
                    and_(
                        OperatorAccessRecord.account_id == OperatorAccessRevisionRecord.account_id,
                        OperatorAccessRecord.current_version
                        == OperatorAccessRevisionRecord.version,
                    ),
                )
                .join(
                    ExternalIdentityRecord,
                    ExternalIdentityRecord.account_id == OperatorAccessRecord.account_id,
                )
                .where(OperatorAccessRecord.account_id == actor_id)
                .with_for_update(of=OperatorAccessRecord)
            )
            if row is not None:
                access = OperatorAccess(row.account_id, row.version, row.active, row.changed_at)
        facts = TriageAuthorityFacts(identity, access, await self.now())
        self.identity.facts = facts
        return facts

    def bind_triage_operator(self, principal: OperatorPrincipal) -> None:
        facts = self.identity.facts
        if (
            facts is None
            or facts.identity != principal.identity
            or facts.access != principal.access
            or self.authority.account_id != principal.identity.session.account_id
            or not principal.identity.session.is_active(facts.checked_at)
            or principal.identity.deleted_at is not None
            or principal.identity.banned
            or not principal.access.is_active(facts.checked_at)
        ):
            raise RuntimeError("Triage principal differs from its actual locked authority facts")
        self.authority.access = principal.access
        self.identity.bound = principal

    def checked_triage_actor(self) -> OperatorAccess:
        if self.identity.bound is None:
            raise RuntimeError("Triage lacks its application-validated actual operator principal")
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

    async def lock_triage_context(self, report_id: UUID) -> ReportTriageSourcePreview | None:
        self.checked_triage_actor()
        if report_id != self.report_id:
            raise RuntimeError("Triage report differs from its ordered lock scope")
        source = self.expected_source
        if source is None:
            current = await report_source(self.session, report_id, lock=True)
            if current is not None:
                raise RuntimeError(
                    "Triage report appeared outside its actual ordered account scope"
                )
            return None
        return await selected_locked_report_preview(self.session, source, lock=True)

    async def stored_triage(self, job_id: UUID) -> StoredReportTriage:
        self.checked_triage_actor()
        return await read_triage_job(self.session, job_id, self.report_id)

    async def replay_triage(
        self, actor_id: UUID, key: IntentKey, digest: bytes
    ) -> TriageIntentObservation:
        if actor_id != self.checked_triage_actor().account_id:
            raise RuntimeError("Triage intent differs from its actual current operator")
        return await read_triage_intent(self.session, actor_id, self.report_id, key, digest)

    async def prepare_triage_source(
        self,
        context: ReportTriageEvidenceContext,
        access: OperatorAccess,
        actor_session_id: UUID,
        at: datetime,
    ) -> PreparedReportTriageSource:
        actor = self.checked_triage_session()
        if (
            context.report.id != self.report_id
            or context.report.target_id != self.target_id
            or access != self.checked_triage_actor()
            or actor_session_id != actor.session.id
        ):
            raise RuntimeError("Triage materialization differs from actual locked source/authority")
        matching = aliased(
            ReportTriageEvidenceRecord,
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
            .subquery(),
        )
        previous_query = (
            select(func.max(ReportTriageEvidenceRecord.version))
            .where(ReportTriageEvidenceRecord.report_id == self.report_id)
            .scalar_subquery()
        )
        one = select(literal(1).label("one")).subquery()
        existing, previous = (
            await self.session.execute(
                select(matching, previous_query).select_from(one).outerjoin(matching, true())
            )
        ).one()
        if existing is not None:
            return PreparedReportTriageSource(triage_snapshot_value(existing, access), True)
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
        return PreparedReportTriageSource(snapshot, False)

    async def admit_triage_submission(self, request: ReportTriageAdmission) -> StoredReportTriage:
        actor = self.checked_triage_session()
        snapshot = request.source.snapshot
        if (
            snapshot.report.id,
            snapshot.report.target_id,
            snapshot.operator,
            snapshot.actor_session_id,
        ) != (self.report_id, self.target_id, self.checked_triage_actor(), actor.session.id):
            raise RuntimeError("Prepared triage differs from its actual locked source/authority")
        return await admit_triage_submission(
            self.session, self.policy, request, self.triage_recorder
        )

    async def latest_triage(self, report_id: UUID) -> StoredReportTriage | None:
        self.checked_triage_actor()
        if report_id != self.report_id:
            raise RuntimeError("Triage inspection differs from actual requested report")
        return await read_latest_triage(self.session, report_id)

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
                    # Every triage use case authenticates through the typed transaction
                    # before role/source access. That lock_identity acquires the sorted
                    # actor/target accounts and session ONCE, retaining the same order.
                    yield SqlOperatorReportTriageTransaction(
                        session,
                        self.recorder,
                        report_id=report_id,
                        target_id=target_id,
                        expected_source=source,
                        actor_secret_digest=actor_secret_digest,
                        triage_recorder=self.triage_recorder,
                        policy=self.policy,
                    )
        except (StorageUnavailableError, TimeoutError):
            raise AiUnavailableError from None
