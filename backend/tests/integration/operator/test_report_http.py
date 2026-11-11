from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.report_router import (
    OperatorReportHttpServices,
    operator_report_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_reports import Reports, reports
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration
ROOT = "/api/v1/operator/reports"


@asynccontextmanager
async def client(api: Reports, viewer: Actor) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-report-inspection")),
    )
    app.include_router(operator_report_router(OperatorReportHttpServices(api.search(), api.read())))
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="https://operator.test",
                cookies={SESSION_COOKIE: viewer.credential.value},
            ) as http,
        ):
            yield http
    finally:
        provider.shutdown()


async def test_real_report_http_audits_exact_sources_and_never_puts_content_in_telemetry(
    identity_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    api = await reports(identity_engine)
    action_id = uuid4()
    async with client(api, api.owner) as http:
        http.headers.update(
            {
                "X-Action-ID": str(action_id),
                "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
            }
        )
        listing = await http.get(
            ROOT,
            params={
                "reporter_id": str(api.reporter.id),
                "target_id": str(api.target.id),
                "category": "other",
            },
        )
        detail = await http.get(f"{ROOT}/{api.report.id}")
        missing = await http.get(f"{ROOT}/{uuid4()}")
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert missing.status_code == HTTPStatus.NOT_FOUND
    assert detail.json()["comment"] == api.report.comment
    assert "comment" not in listing.json()["reports"][0]
    assert detail.json()["context"]["goal_id"] == str(api.report.context.snapshot.goal_id)
    assert detail.json()["submission"] is not None
    # Read-time request origin is NOT a fallback for absent original submission/disclosure origin.
    assert detail.json()["submission"]["origin"]["http_request_id"] is None
    assert detail.json()["context"]["origin"]["http_request_id"] is None
    for response in (listing, detail, missing):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        request_id = UUID(response.headers["X-Request-ID"])
        async with api.uow.sessions() as session:
            audit = (
                await session.scalars(
                    select(OperatorAuditRecord).where(
                        OperatorAuditRecord.http_request_id == request_id
                    )
                )
            ).one()
            event = (
                await session.scalars(
                    select(ProductEventRecord).where(
                        ProductEventRecord.operator_audit_id == audit.id
                    )
                )
            ).one()
            assert audit.action_id == action_id
            assert event.request_id == request_id
            assert audit.trace_id == "a" * 32
            assert event.action_id == action_id
    records = [record for record in caplog.records if record.name == "studymate.http"]
    assert len(records) == len((listing, detail, missing))
    assert api.report.comment is not None
    assert api.report.comment not in repr([record.__dict__ for record in records])


async def test_real_http_absent_role_no_cookie_and_closed_query_never_audit_data(
    identity_engine: AsyncEngine,
) -> None:
    api = await reports(identity_engine)
    async with client(api, api.reporter) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(ROOT)).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(f"{ROOT}/{api.report.id}")).status_code == HTTPStatus.UNAUTHORIZED
    async with client(api, api.owner) as http:
        invalid = await http.get(ROOT, params={"comment": "Private-injected-term"})
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "Private-injected-term" not in invalid.text
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
