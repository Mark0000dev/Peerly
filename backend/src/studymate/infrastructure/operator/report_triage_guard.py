"""Same-transaction worker authority/source checks; never grants student AI permission."""

import hmac
from dataclasses import dataclass

from sqlalchemy import DateTime, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.ai.jobs import AiJob, Failure
from studymate.domain.ai.tasks import TriageReport
from studymate.domain.operator.report_triage import ReportTriageEvidenceSnapshot
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
)
from studymate.infrastructure.operator.report_triage_models import (
    ReportTriageEvidenceRecord,
    ReportTriageSubmissionRecord,
)
from studymate.infrastructure.operator.report_triage_sources import selected_report_preview
from studymate.infrastructure.operator.report_triage_values import triage_snapshot_value
from studymate.infrastructure.persistence.identity_claims import identity_lineage_banned
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    SessionRecord,
)
from studymate.infrastructure.report_moderation.transactions import report_source


async def current_triage_grant(
    session: AsyncSession, job: AiJob, source: ReportTriageEvidenceRecord, *, lock: bool
) -> OperatorAccessRevisionRecord | None:
    if lock:
        await session.execute(
            select(AccountRecord.id)
            .where(AccountRecord.id.in_((job.actor_id, source.target_id)))
            .order_by(AccountRecord.id)
            .with_for_update(key_share=True)
        )
    account = (
        await session.execute(
            select(AccountRecord.deleted_at, AccountRecord.banned_at).where(
                AccountRecord.id == job.actor_id
            )
        )
    ).one_or_none()
    if (
        account is None
        or account.deleted_at is not None
        or account.banned_at is not None
        or await identity_lineage_banned(session, job.actor_id)
    ):
        return None
    google = await session.scalar(
        select(ExternalIdentityRecord.id).where(
            ExternalIdentityRecord.account_id == job.actor_id,
            ExternalIdentityRecord.retired_at.is_(None),
        )
    )
    if google is None:
        return None
    session_query = select(
        SessionRecord.account_id,
        SessionRecord.issued_at,
        SessionRecord.expires_at,
        SessionRecord.revoked_at,
    ).where(SessionRecord.id == source.actor_session_id)
    if lock:
        session_query = session_query.with_for_update()
    actor_session = (await session.execute(session_query)).one_or_none()
    at = (
        await session.execute(select(func.clock_timestamp(type_=DateTime(timezone=True))))
    ).scalar_one()
    if (
        actor_session is None
        or actor_session.account_id != job.actor_id
        or actor_session.revoked_at is not None
        or not actor_session.issued_at <= at < actor_session.expires_at
    ):
        return None
    grant_query = (
        select(OperatorAccessRevisionRecord)
        .join(
            OperatorAccessRecord,
            and_(
                OperatorAccessRecord.account_id == OperatorAccessRevisionRecord.account_id,
                OperatorAccessRecord.current_version == OperatorAccessRevisionRecord.version,
            ),
        )
        .where(OperatorAccessRecord.account_id == job.actor_id)
    )
    if lock:
        grant_query = grant_query.with_for_update(of=OperatorAccessRecord)
    grant = await session.scalar(grant_query)
    if (
        grant is None
        or not grant.active
        or grant.version != source.operator_access_version
        or grant.changed_at > at
        or source.operator_id != job.actor_id
    ):
        return None
    return grant


async def selected_triage_source_failure(
    session: AsyncSession, snapshot: ReportTriageEvidenceSnapshot, task: TriageReport, *, lock: bool
) -> Failure | None:
    if task != snapshot.task:
        return Failure.STALE_SOURCE
    source = await report_source(session, snapshot.report.id, lock=lock)
    if source is None or source != snapshot.report:
        return Failure.STALE_SOURCE
    current = (await selected_report_preview(session, source)).context
    if (
        current is None
        or current.review_version != snapshot.review_version
        or not hmac.compare_digest(current.evidence_digest, snapshot.evidence_digest)
    ):
        return Failure.STALE_SOURCE
    return None


@dataclass(frozen=True, slots=True)
class SqlReportTriageSourceGuard:
    async def check(
        self, session: AsyncSession, job: AiJob, *, lock: bool = True
    ) -> Failure | None:
        if not isinstance(job.task, TriageReport):
            return Failure.INVALID_INPUT
        proof = await session.get(ReportTriageSubmissionRecord, job.id)
        if proof is None or proof.operator_id != job.actor_id:
            return Failure.ACCOUNT
        source = await session.get(
            ReportTriageEvidenceRecord, (job.task.source.id, job.task.source.version)
        )
        if source is None or (proof.report_id, proof.source_version) != (
            source.report_id,
            source.version,
        ):
            return Failure.STALE_SOURCE
        grant = await current_triage_grant(session, job, source, lock=lock)
        if grant is None:
            return Failure.ACCOUNT
        return await selected_triage_source_failure(
            session, triage_snapshot_value(source, grant), job.task, lock=lock
        )
