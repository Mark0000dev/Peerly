"""Consistent current authority/evidence observation; native locking guard is separate."""

import hmac
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import DateTime, Nullable, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.ai.jobs import AiJob, Failure
from studymate.domain.ai.tasks import TriageReport
from studymate.domain.operator.profile_reports import OperatorReportKind
from studymate.domain.operator.report_triage import ReportTriageEvidenceSnapshot
from studymate.domain.report_moderation.reviews import ReviewReportSource
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
)
from studymate.infrastructure.operator.report_triage_models import (
    ReportTriageEvidenceRecord,
    ReportTriageSubmissionRecord,
)
from studymate.infrastructure.operator.report_triage_sources import (
    SelectedReportRows,
    selected_report_preview_value,
)
from studymate.infrastructure.operator.report_triage_values import triage_snapshot_value
from studymate.infrastructure.persistence.identity_claims import identity_lineage_banned
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.profile_models import ProfileRevisionRecord
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)
from studymate.infrastructure.report_moderation.models import ReportReviewRevisionRecord


@dataclass(frozen=True, slots=True)
class ObservedTriageRows:
    submission: ReportTriageSubmissionRecord
    evidence: ReportTriageEvidenceRecord | None
    access: OperatorAccessRevisionRecord | None
    account: AccountRecord | None
    actor_session: SessionRecord | None
    has_google: bool
    at: datetime
    report: ProfileReportRecord | None
    profile_context: ProfileAccessRecord | None
    message_context: MessageReportContextRecord | None
    message: MessageRecord | None
    profile: ProfileRevisionRecord | None
    review_version: int | None


async def read_observed_rows(session: AsyncSession, job: AiJob) -> ObservedTriageRows | None:
    proof, source, grant = (
        ReportTriageSubmissionRecord,
        ReportTriageEvidenceRecord,
        OperatorAccessRevisionRecord,
    )
    latest_review = (
        select(func.max(ReportReviewRevisionRecord.version))
        .where(ReportReviewRevisionRecord.report_id == job.task.source.id)
        .scalar_subquery()
    )
    google = (
        select(ExternalIdentityRecord.id)
        .where(
            ExternalIdentityRecord.account_id == job.actor_id,
            ExternalIdentityRecord.retired_at.is_(None),
        )
        .exists()
    )
    row = (
        await session.execute(
            select(
                proof,
                Nullable(source),
                Nullable(grant),
                Nullable(AccountRecord),
                Nullable(SessionRecord),
                google,
                func.clock_timestamp(type_=DateTime(timezone=True)),
                Nullable(ProfileReportRecord),
                Nullable(ProfileAccessRecord),
                Nullable(MessageReportContextRecord),
                Nullable(MessageRecord),
                Nullable(ProfileRevisionRecord),
                latest_review,
            )
            .select_from(proof)
            .outerjoin(
                source,
                and_(source.report_id == proof.report_id, source.version == proof.source_version),
            )
            .outerjoin(AccountRecord, AccountRecord.id == job.actor_id)
            .outerjoin(SessionRecord, SessionRecord.id == source.actor_session_id)
            .outerjoin(OperatorAccessRecord, OperatorAccessRecord.account_id == job.actor_id)
            .outerjoin(
                grant,
                and_(
                    grant.account_id == OperatorAccessRecord.account_id,
                    grant.version == OperatorAccessRecord.current_version,
                ),
            )
            .outerjoin(ProfileReportRecord, ProfileReportRecord.id == source.report_id)
            .outerjoin(
                ProfileAccessRecord, ProfileAccessRecord.id == ProfileReportRecord.context_id
            )
            .outerjoin(
                MessageReportContextRecord,
                MessageReportContextRecord.id == ProfileReportRecord.message_context_id,
            )
            .outerjoin(MessageRecord, MessageRecord.id == MessageReportContextRecord.message_id)
            .outerjoin(
                ProfileRevisionRecord,
                and_(
                    ProfileRevisionRecord.account_id == ProfileAccessRecord.target_id,
                    ProfileRevisionRecord.version == ProfileAccessRecord.profile_version,
                ),
            )
            .where(proof.job_id == job.id)
        )
    ).one_or_none()
    if row is None:
        return None
    (
        submission,
        evidence,
        access,
        account,
        actor_session,
        has_google,
        at,
        report,
        profile_context,
        message_context,
        message,
        profile,
        review_version,
    ) = row
    return ObservedTriageRows(
        submission,
        evidence,
        access,
        account,
        actor_session,
        has_google,
        at,
        report,
        profile_context,
        message_context,
        message,
        profile,
        review_version,
    )


def observed_authority_current(
    rows: ObservedTriageRows,
    source: ReportTriageEvidenceRecord,
    access: OperatorAccessRevisionRecord,
    job: AiJob,
) -> bool:
    account, actor_session, at = rows.account, rows.actor_session, rows.at
    return (
        account is not None
        and account.deleted_at is None
        and account.banned_at is None
        and rows.has_google
        and actor_session is not None
        and actor_session.account_id == job.actor_id
        and actor_session.revoked_at is None
        and actor_session.issued_at <= at < actor_session.expires_at
        and access.active
        and access.version == source.operator_access_version
        and access.changed_at <= at
        and source.operator_id == job.actor_id
    )


def observed_evidence_current(
    rows: ObservedTriageRows, snapshot: ReportTriageEvidenceSnapshot
) -> bool:
    report, profile_context, message_context = (
        rows.report,
        rows.profile_context,
        rows.message_context,
    )
    if report is None:
        return False
    profile_report = report.kind == OperatorReportKind.PROFILE.value
    context_id = report.context_id if profile_report else report.message_context_id
    target_id = (
        profile_context.target_id
        if profile_report and profile_context is not None
        else message_context.target_id
        if message_context is not None
        else None
    )
    if context_id is None or target_id is None:
        return False
    current = ReviewReportSource(
        report.id, OperatorReportKind(report.kind), report.reporter_id, target_id, context_id
    )
    if current != snapshot.report:
        return False
    selected = selected_report_preview_value(
        current,
        SelectedReportRows(
            report,
            profile_context,
            message_context,
            rows.message,
            rows.profile,
            rows.review_version,
        ),
    ).context
    return (
        selected is not None
        and selected.review_version == snapshot.review_version
        and hmac.compare_digest(selected.evidence_digest, snapshot.evidence_digest)
    )


async def observe_report_triage_source(session: AsyncSession, job: AiJob) -> Failure | None:
    if not isinstance(job.task, TriageReport):
        return Failure.INVALID_INPUT
    rows = await read_observed_rows(session, job)
    if rows is None or rows.submission.operator_id != job.actor_id:
        return Failure.ACCOUNT
    source = rows.evidence
    if source is None or (rows.submission.report_id, rows.submission.source_version) != (
        job.task.source.id,
        job.task.source.version,
    ):
        return Failure.STALE_SOURCE
    access = rows.access
    if (
        access is None
        or not observed_authority_current(rows, source, access, job)
        or await identity_lineage_banned(session, job.actor_id)
    ):
        return Failure.ACCOUNT
    snapshot = triage_snapshot_value(source, access)
    if job.task != snapshot.task:
        return Failure.STALE_SOURCE
    return None if observed_evidence_current(rows, snapshot) else Failure.STALE_SOURCE
