"""Existing audited report routes expose actual image evidence without profile placeholders."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.discovery.profiles import ReadDiscoveryProfile
from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.operator.profile_reports import (
    ReadOperatorProfileReport,
    SearchOperatorProfileReports,
)
from studymate.application.operator.report_ports import OperatorReportFilters
from studymate.application.safety.profile_reports import (
    SubmitProfileReport,
    SubmitProfileReportCommand,
)
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.profile_reports import (
    OperatorMessageImageReportDetail,
    OperatorReportKind,
)
from studymate.domain.reports import ReportCategory
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.report_cursors import FernetOperatorReportCursorCodec
from studymate.infrastructure.operator.report_transactions import SqlOperatorReportUnitOfWork
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileUnitOfWork
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.persistence.profile_reports import SqlProfileReportUnitOfWork
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.report_router import (
    OperatorReportHttpServices,
    operator_report_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.safety.message_reports.fixture import prepared
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration
CODEC = FernetOperatorReportCursorCodec.from_key(b"r" * 32)


def search(uow: SqlOperatorReportUnitOfWork) -> SearchOperatorProfileReports:
    return SearchOperatorProfileReports(uow, HASHER, FINGERPRINTER, CODEC)


@asynccontextmanager
async def client(uow: SqlOperatorReportUnitOfWork, viewer: Actor) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_report_router(
            OperatorReportHttpServices(search(uow), ReadOperatorProfileReport(uow, HASHER))
        )
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://operator.test",
            cookies={SESSION_COOKIE: viewer.credential.value},
        ) as http,
    ):
        yield http


async def test_unified_report_list_and_filters_include_both_actual_evidence_kinds(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    image_report = await api.submit()(api.command())
    profile = await ReadDiscoveryProfile(
        SqlDiscoveryProfileUnitOfWork(api.chat.api.sessions), HASHER
    )(api.chat.recipient.credential, api.chat.sender.id)
    profile_report = await SubmitProfileReport(
        SqlProfileReportUnitOfWork(api.chat.api.sessions), HASHER, FINGERPRINTER
    )(
        SubmitProfileReportCommand(
            api.chat.recipient.credential,
            profile.access_context.id,
            ReportCategory.SPAM,
            IntentKey("profile-in-unified-list"),
        )
    )
    viewer = await operator(identity_engine)
    uow = SqlOperatorReportUnitOfWork(api.chat.api.sessions, record_operator_audit)
    page = await search(uow)(viewer.credential, OperatorReportFilters(target_id=api.chat.sender.id))
    assert {row.id for row in page.reports} == {image_report.id, profile_report.id}
    assert {row.kind for row in page.reports} == {
        OperatorReportKind.PROFILE,
        OperatorReportKind.MESSAGE_IMAGE,
    }
    filtered = await search(uow)(
        viewer.credential, OperatorReportFilters(context_id=api.context.id)
    )
    assert len(filtered.reports) == 1
    assert filtered.reports[0].kind == OperatorReportKind.MESSAGE_IMAGE
    assert filtered.reports[0].context_id == api.context.id
    assert not (
        await search(uow)(viewer.credential, OperatorReportFilters(context_id=uuid4()))
    ).reports
    detail = await ReadOperatorProfileReport(uow, HASHER)(viewer.credential, image_report.id)
    assert isinstance(detail, OperatorMessageImageReportDetail)
    assert detail.context.source == api.context.source
    assert detail.comment == image_report.comment
    assert detail.submission is not None
    assert detail.submission.reporter_id == api.chat.recipient.id


async def test_existing_http_report_detail_has_honest_tagged_image_context_after_actor_deletion(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    report = await api.submit()(api.command())
    viewer = await operator(identity_engine)
    uow = SqlOperatorReportUnitOfWork(api.chat.api.sessions, record_operator_audit)
    async with api.chat.api.sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id.in_((api.chat.sender.id, api.chat.recipient.id)))
            .values(banned_at=func.clock_timestamp(), deleted_at=func.clock_timestamp())
        )
    async with client(uow, viewer) as http:
        response = await http.get(f"/api/v1/operator/reports/{report.id}")
        listing = await http.get("/api/v1/operator/reports")
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["report"]["kind"] == "message_image"
    assert body["context"]["kind"] == "message_image"
    assert body["context"]["message_id"] == str(api.context.source.message_id)
    assert api.context.source.image is not None
    assert body["context"]["image_id"] == str(api.context.source.image.id)
    assert body["comment"] == report.comment
    for forbidden in (
        "profile_version",
        "photo_version",
        "source_sha256",
        "display_sha256",
        "text",
        "url",
    ):
        assert forbidden not in body["context"]
    assert listing.status_code == HTTPStatus.OK
    assert listing.json()["reports"][0]["kind"] == "message_image"
    assert "comment" not in listing.json()["reports"][0]
    async with api.chat.api.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert {audit.action for audit in audits} == {"read_report", "search_reports"}
        assert all(audit.operator_id == viewer.id for audit in audits)


async def test_image_report_body_is_withheld_when_actual_read_audit_fails(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    report = await api.submit()(api.command())
    viewer = await operator(identity_engine)

    async def failing(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    uow = SqlOperatorReportUnitOfWork(api.chat.api.sessions, failing)
    async with client(uow, viewer) as http:
        response = await http.get(f"/api/v1/operator/reports/{report.id}")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert report.comment is not None
    assert report.comment not in response.text
    async with api.chat.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OperatorAuditRecord)) == 0
