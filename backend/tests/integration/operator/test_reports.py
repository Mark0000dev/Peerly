"""Actual retained profile reports under paired main0040, with one canonical audit."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.application.operator.profile_reports import (
    ReadOperatorProfileReport,
    SearchOperatorProfileReports,
)
from studymate.application.operator.report_ports import OperatorReportFilters
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.profile_reports import OPERATOR_REPORT_PAGE_SIZE
from studymate.domain.reports import ProfileReport, ReportCategory
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.report_cursors import FernetOperatorReportCursorCodec
from studymate.infrastructure.operator.report_transactions import SqlOperatorReportUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.safety_fixture import prepared
from tests.integration.student_actor import Actor
from tests.integration.test_profile_reports import command, service

pytestmark = pytest.mark.integration
CODEC = FernetOperatorReportCursorCodec.from_key(b"r" * 32)
RAW_COMMENT = "  Exact private legacy comment\n retained without normalization  "


@dataclass(frozen=True, slots=True)
class Reports:
    owner: Actor
    reporter: Actor
    target: Actor
    report: ProfileReport
    uow: SqlOperatorReportUnitOfWork

    def search(self) -> SearchOperatorProfileReports:
        return SearchOperatorProfileReports(self.uow, HASHER, FINGERPRINTER, CODEC)

    def read(self) -> ReadOperatorProfileReport:
        return ReadOperatorProfileReport(self.uow, HASHER)


async def reports(engine: AsyncEngine) -> Reports:
    reporter, target, context = await prepared(engine)
    report = await service(engine)(command(reporter, context))
    owner = await operator(engine)
    unit = SqlOperatorReportUnitOfWork(
        async_sessionmaker(engine, expire_on_commit=False), record_operator_audit
    )
    return Reports(owner, reporter, target, report, unit)


async def test_full_privileged_report_preserves_raw_history_and_separate_origins(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    context_request, submission_request = uuid4(), uuid4()
    legacy_at = api.report.context.issued_at - timedelta(seconds=1)
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(ProfileReportRecord)
            .where(ProfileReportRecord.id == api.report.id)
            .values(comment=RAW_COMMENT, submitted_at=legacy_at)
        )
        await session.execute(
            update(ProfileAccessRecord)
            .where(ProfileAccessRecord.id == api.report.context.id)
            .values(request_id=context_request)
        )
        await session.execute(
            update(ProductEventRecord)
            .where(ProductEventRecord.report_id == api.report.id)
            .values(request_id=submission_request)
        )
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id.in_((api.reporter.id, api.target.id)))
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    detail = await api.read()(api.owner.credential, api.report.id)
    assert detail is not None
    assert detail.comment == RAW_COMMENT
    assert detail.context == api.report.context
    assert detail.report.submitted_at == legacy_at
    assert detail.context_origin.http_request_id == context_request
    assert detail.submission is not None
    assert detail.submission.origin.http_request_id == submission_request
    assert detail.submission.report_id == api.report.id
    async with api.uow.sessions() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        ).one()
        assert audit.operator_id == api.owner.id
        assert audit.action == "read_report"
        assert audit.resource_kind == "report"
        assert audit.result_ids == [api.report.id]
        assert event.operator_audit_id == audit.id
        assert event.operator_action == "read_report"
        assert RAW_COMMENT not in repr(audit)
        assert RAW_COMMENT not in repr(event)


async def test_absent_canonical_submission_stays_null_not_context_origin(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    legacy_id = uuid4()
    async with api.uow.sessions.begin() as session:
        session.add(
            ProfileReportRecord(
                id=legacy_id,
                reporter_id=api.reporter.id,
                context_id=api.report.context.id,
                category="spam",
                comment=None,
                submitted_at=api.report.submitted_at,
            )
        )
        await session.execute(
            update(ProfileAccessRecord)
            .where(ProfileAccessRecord.id == api.report.context.id)
            .values(request_id=uuid4())
        )
    detail = await api.read()(api.owner.credential, legacy_id)
    assert detail is not None
    assert detail.comment is None
    assert detail.submission is None
    assert detail.context_origin.http_request_id is not None


async def test_metadata_search_real_filters_and_half_open_time_bounds(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    filters = OperatorReportFilters(
        api.reporter.id,
        api.target.id,
        api.report.context.id,
        ReportCategory.OTHER,
        api.report.submitted_at,
        api.report.submitted_at + timedelta(microseconds=1),
    )
    page = await api.search()(api.owner.credential, filters)
    assert tuple(row.id for row in page.reports) == (api.report.id,)
    assert page.reports[0].has_comment
    assert not hasattr(page.reports[0], "comment")
    excluded = await api.search()(
        api.owner.credential, OperatorReportFilters(submitted_before=api.report.submitted_at)
    )
    assert excluded.reports == ()
    for changed in (
        OperatorReportFilters(reporter_id=uuid4()),
        OperatorReportFilters(target_id=uuid4()),
        OperatorReportFilters(context_id=uuid4()),
        OperatorReportFilters(category=ReportCategory.SPAM),
    ):
        assert (await api.search()(api.owner.credential, changed)).reports == ()
    async with api.uow.sessions() as session:
        inspections = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert all(row.action == "search_reports" for row in inspections)
        assert all(row.query_fingerprint is not None for row in inspections)
        assert inspections[0].result_ids == [api.report.id]


async def test_pagination_is_bounded_actor_filter_scoped_metadata_anchor_not_replay(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    ids = {uuid4() for _ in range(OPERATOR_REPORT_PAGE_SIZE + 1)}
    async with api.uow.sessions.begin() as session:
        for report_id in ids:
            session.add(
                ProfileReportRecord(
                    id=report_id,
                    reporter_id=api.reporter.id,
                    context_id=api.report.context.id,
                    category="spam",
                    comment=RAW_COMMENT,
                    submitted_at=api.report.submitted_at - timedelta(seconds=1),
                )
            )
    first = await api.search()(api.owner.credential, OperatorReportFilters())
    assert len(first.reports) == OPERATOR_REPORT_PAGE_SIZE
    assert first.next_cursor is not None
    newer_id = uuid4()
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        session.add(
            ProfileReportRecord(
                id=newer_id,
                reporter_id=api.reporter.id,
                context_id=api.report.context.id,
                category="spam",
                comment=None,
                submitted_at=now,
            )
        )
    second = await api.search()(api.owner.credential, OperatorReportFilters(), first.next_cursor)
    combined = tuple(row.id for row in first.reports + second.reports)
    assert set(combined) == ids | {api.report.id}
    assert len(combined) == len(set(combined))
    assert second.next_cursor is None
    assert newer_id not in combined
    assert (await api.search()(api.owner.credential, OperatorReportFilters())).reports[
        0
    ].id == newer_id
    with pytest.raises(InvalidOperatorCursorError):
        await api.search()(
            api.owner.credential,
            OperatorReportFilters(category=ReportCategory.SPAM),
            first.next_cursor,
        )
    other_operator = await operator(identity_engine)
    with pytest.raises(InvalidOperatorCursorError):
        await api.search()(other_operator.credential, OperatorReportFilters(), first.next_cursor)


@pytest.mark.parametrize("access", ["absent", "revoked"])
async def test_report_queries_require_explicit_current_db_role(
    identity_engine: AsyncEngine, access: str
) -> None:
    api = await reports(identity_engine)
    viewer = api.reporter if access == "absent" else await operator(identity_engine, active=False)
    with pytest.raises(OperatorAccessDeniedError):
        await api.read()(viewer.credential, api.report.id)
    with pytest.raises(OperatorAccessDeniedError):
        await api.search()(viewer.credential, OperatorReportFilters())
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_missing_report_and_empty_search_commit_actual_canonical_audits(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    missing = uuid4()
    assert await api.read()(api.owner.credential, missing) is None
    assert (
        await api.search()(api.owner.credential, OperatorReportFilters(target_id=uuid4()))
    ).reports == ()
    async with api.uow.sessions() as session:
        rows = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert {row.outcome for row in rows} == {"not_found", "search"}
        assert all(row.result_ids == [] for row in rows)
        assert {row.requested_id for row in rows} == {missing, None}
        events = tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
        assert {row.operator_audit_id for row in events} == {row.id for row in rows}


@pytest.mark.parametrize("cancel", [False, True])
async def test_no_private_report_response_when_canonical_commit_fails_or_cancels(
    identity_engine: AsyncEngine, cancel: bool
) -> None:
    api = await reports(identity_engine)

    async def failing(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        if cancel:
            raise asyncio.CancelledError
        raise RuntimeError("Synthetic canonical failure")

    unit = SqlOperatorReportUnitOfWork(api.uow.sessions, failing)
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await ReadOperatorProfileReport(unit, HASHER)(api.owner.credential, api.report.id)
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
    assert await api.read()(api.owner.credential, api.report.id) is not None


async def test_actual_db_clock_expiry_after_report_audit_rolls_back_private_response(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    async with api.uow.sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == api.owner.id)
            .values(expires_at=now + timedelta(seconds=1))
        )

    entered = False

    async def expires(session: AsyncSession, audit: OperatorAudit) -> None:
        nonlocal entered
        await record_operator_audit(session, audit)
        entered = True
        await session.execute(select(func.pg_sleep(1.1)))

    unit = SqlOperatorReportUnitOfWork(api.uow.sessions, expires)
    with pytest.raises(UnauthenticatedError):
        await ReadOperatorProfileReport(unit, HASHER)(api.owner.credential, api.report.id)
    assert entered
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
