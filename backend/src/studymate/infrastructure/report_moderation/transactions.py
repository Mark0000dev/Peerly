"""Actual report locks, immutable human proof and canonical callback in one transaction."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.report_moderation.ports import ReportReviewIntent
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.profile_reports import OperatorReportKind
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.report_moderation.reviews import (
    REVIEW_HISTORY_PAGE_SIZE,
    ReportReviewAction,
    ReportReviewRevision,
    ReviewReportSource,
)
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.operator.models import OperatorAccessRevisionRecord
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.report_moderation.models import (
    ReportReviewIntentRecord,
    ReportReviewRevisionRecord,
)


class ReportReviewRecorder(Protocol):
    async def __call__(self, session: AsyncSession, source: ReportReviewRevision) -> None: ...


async def report_source(
    session: AsyncSession, report_id: UUID, *, lock: bool = False
) -> ReviewReportSource | None:
    report, profile, message = (
        ProfileReportRecord,
        ProfileAccessRecord,
        MessageReportContextRecord,
    )
    statement = (
        select(
            report.id,
            report.kind,
            report.reporter_id,
            func.coalesce(profile.target_id, message.target_id),
            func.coalesce(report.context_id, report.message_context_id),
        )
        .outerjoin(profile, profile.id == report.context_id)
        .outerjoin(message, message.id == report.message_context_id)
        .where(report.id == report_id)
    )
    if lock:
        statement = statement.with_for_update(of=report)
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    id_, kind, reporter, target, context = row
    if context is None:
        raise RuntimeError("Report review is missing its actual immutable evidence context")
    return ReviewReportSource(id_, OperatorReportKind(kind), reporter, target, context)


def review_value(
    row: ReportReviewRevisionRecord, grant: OperatorAccessRevisionRecord
) -> ReportReviewRevision:
    return ReportReviewRevision(
        row.id,
        row.report_id,
        row.version,
        row.previous_version,
        ReportReviewAction(row.action),
        row.reason,
        OperatorAccess(grant.account_id, grant.version, grant.active, grant.changed_at),
        row.actor_session_id,
        row.reviewed_at,
        row.event_id,
        OperatorEventOrigin(row.http_request_id, row.action_id, row.trace_id, row.span_id),
    )


@dataclass(slots=True)
class ReviewIdentity:
    original: IdentitySnapshot | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SqlReportModerationTransaction(SqlOperatorTransaction):
    report_id: UUID
    target_id: UUID | None
    review_recorder: ReportReviewRecorder
    identity: ReviewIdentity = field(default_factory=ReviewIdentity)

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        original = (
            await self.lock_identity_for_peer(secret_digest, self.target_id)
            if self.target_id is not None
            else await SqlIdentityTransaction.lock_identity(self, secret_digest)
        )
        self.identity.original = original
        return original

    def checked_scope(self, report_id: UUID) -> IdentitySnapshot:
        access = self.checked_access()
        actor = self.identity.original
        if (
            actor is None
            or actor.session.account_id != access.account_id
            or report_id != self.report_id
        ):
            raise RuntimeError("Report review scope differs from actual actor/report locks")
        return actor

    async def lock_report(self, report_id: UUID) -> ReviewReportSource | None:
        self.checked_scope(report_id)
        source = await report_source(self.session, report_id, lock=True)
        if source is not None and source.target_id != self.target_id:
            raise RuntimeError("Report review target differs from its ordered account locks")
        return source

    async def latest_review(self, report_id: UUID) -> ReportReviewRevision | None:
        rows = await self.review_history(report_id, (1 << 31) - 1, None)
        return rows[0] if rows else None

    async def review_history(
        self, report_id: UUID, anchor: int, before: int | None
    ) -> tuple[ReportReviewRevision, ...]:
        self.checked_scope(report_id)
        source, grant = ReportReviewRevisionRecord, OperatorAccessRevisionRecord
        statement = (
            select(source, grant)
            .join(
                grant,
                and_(
                    grant.account_id == source.operator_id,
                    grant.version == source.operator_access_version,
                ),
            )
            .where(source.report_id == report_id, source.version <= anchor)
        )
        if before is not None:
            statement = statement.where(source.version < before)
        rows = await self.session.execute(
            statement.order_by(source.version.desc()).limit(REVIEW_HISTORY_PAGE_SIZE + 1)
        )
        return tuple(review_value(row, original) for row, original in rows)

    async def prior_review(self, actor_id: UUID, key: IntentKey) -> ReportReviewIntent | None:
        actor = self.checked_scope(self.report_id)
        if actor.session.account_id != actor_id:
            raise RuntimeError("Report review receipt actor differs from authenticated identity")
        receipt = await self.session.get(ReportReviewIntentRecord, (actor_id, key.value))
        if receipt is None:
            return None
        row = (
            await self.session.execute(
                select(ReportReviewRevisionRecord, OperatorAccessRevisionRecord)
                .join(
                    OperatorAccessRevisionRecord,
                    and_(
                        OperatorAccessRevisionRecord.account_id
                        == ReportReviewRevisionRecord.operator_id,
                        OperatorAccessRevisionRecord.version
                        == ReportReviewRevisionRecord.operator_access_version,
                    ),
                )
                .where(ReportReviewRevisionRecord.id == receipt.review_id)
            )
        ).one()
        return ReportReviewIntent(receipt.fingerprint, review_value(*row))

    async def append_review(
        self, source: ReportReviewRevision, key: IntentKey, fingerprint: bytes
    ) -> ReportReviewRevision:
        actor = self.checked_scope(source.report_id)
        if source.operator != self.checked_access() or source.actor_session_id != actor.session.id:
            raise RuntimeError("Report review source differs from actual session/current grant")
        origin = current_origin()
        actual = replace(
            source,
            origin=OperatorEventOrigin(
                origin.request_id, origin.action_id, origin.trace_id, origin.span_id
            )
            if origin is not None
            else OperatorEventOrigin(),
        )
        self.session.add(
            ReportReviewRevisionRecord(
                id=actual.id,
                report_id=actual.report_id,
                version=actual.version,
                previous_version=actual.previous_version,
                action=actual.action.value,
                reason=actual.reason,
                operator_id=actual.operator.account_id,
                operator_access_version=actual.operator.version,
                operator_access_active=actual.operator.active,
                actor_session_id=actual.actor_session_id,
                reviewed_at=actual.reviewed_at,
                event_id=actual.event_id,
                event_kind="report.reviewed",
                http_request_id=actual.origin.http_request_id,
                action_id=actual.origin.action_id,
                trace_id=actual.origin.trace_id,
                span_id=actual.origin.span_id,
            )
        )
        await self.session.flush()
        await self.review_recorder(self.session, actual)
        self.session.add(
            ReportReviewIntentRecord(
                operator_id=actual.operator.account_id,
                key=key.value,
                review_id=actual.id,
                fingerprint=fingerprint,
            )
        )
        await self.session.flush()
        return actual


@dataclass(frozen=True, slots=True)
class SqlReportModerationUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder
    review_recorder: ReportReviewRecorder

    @asynccontextmanager
    async def transaction(
        self, actor_secret_digest: bytes, report_id: UUID
    ) -> AsyncIterator[SqlReportModerationTransaction]:
        async with open_transaction(self.sessions) as session:
            source = await report_source(session, report_id)
            target_id = source.target_id if source is not None else None
            identity = SqlIdentityTransaction(session)
            if target_id is not None:
                await identity.lock_identity_for_peer(actor_secret_digest, target_id)
            else:
                await identity.lock_identity(actor_secret_digest)
            yield SqlReportModerationTransaction(
                session,
                self.recorder,
                report_id=report_id,
                target_id=target_id,
                review_recorder=self.review_recorder,
            )
