from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.profile_models import ProfileRevisionRecord
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.profile_history_router import (
    OperatorProfileHistoryHttpServices,
    operator_profile_history_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_profile_history import RAW_ABOUT, RAW_NAME, History, prepared
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration


@asynccontextmanager
async def client(api: History, viewer: Actor) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-profile-history")),
    )
    app.include_router(
        operator_profile_history_router(OperatorProfileHistoryHttpServices(api.read()))
    )
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


async def test_actual_profile_history_http_commits_account_audit_and_only_safe_telemetry(
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(ProfileRevisionRecord)
            .where(
                ProfileRevisionRecord.account_id == api.target.id,
                ProfileRevisionRecord.version == 1,
            )
            .values(display_name=RAW_NAME, about=RAW_ABOUT)
        )
        original_events = await session.scalar(select(func.count()).select_from(ProductEventRecord))
    action_id = uuid4()
    async with client(api, api.owner) as http:
        http.headers.update(
            {
                "X-Action-ID": str(action_id),
                "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
            }
        )
        response = await http.get(f"/api/v1/operator/accounts/{api.target.id}/profile-history")
    assert response.status_code == HTTPStatus.OK, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.json()["account_id"] == str(api.target.id)
    assert [row["version"] for row in response.json()["revisions"]] == [3, 2, 1]
    assert response.json()["revisions"][-1]["display_name"] == RAW_NAME
    assert response.json()["revisions"][-1]["about"] == RAW_ABOUT
    assert response.json()["revisions"][-1]["languages"] == ["ms", "en"]
    request_id = UUID(response.headers["X-Request-ID"])
    async with api.uow.sessions() as session:
        inspection = (await session.scalars(select(OperatorAuditRecord))).one()
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        ).one()
        assert inspection.http_request_id == request_id
        assert inspection.action_id == action_id
        assert inspection.trace_id == "a" * 32
        assert inspection.action == "read_account"
        assert inspection.requested_id == api.target.id
        assert inspection.result_ids == [api.target.id]
        assert event.operator_audit_id == inspection.id
        assert event.request_id == request_id
        assert original_events is not None
        assert (
            await session.scalar(select(func.count()).select_from(ProductEventRecord))
            == original_events + 1
        )
    records = [record for record in caplog.records if record.name == "studymate.http"]
    assert len(records) == 1
    assert RAW_NAME not in repr([record.__dict__ for record in records])
    assert RAW_ABOUT not in repr([record.__dict__ for record in records])


async def test_real_existing_empty_profile_history_and_audited404_no_role_fallback(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    empty = await actor(identity_engine)
    async with client(api, api.owner) as http:
        response = await http.get(f"/api/v1/operator/accounts/{empty.id}/profile-history")
        assert response.status_code == HTTPStatus.OK
        assert response.json()["revisions"] == []
        assert response.json()["anchor_version"] == 0
        missing_id = uuid4()
        missing = await http.get(f"/api/v1/operator/accounts/{missing_id}/profile-history")
        assert missing.status_code == HTTPStatus.NOT_FOUND
    async with client(api, api.target) as http:
        http.headers["X-Operator"] = "true"
        denied = await http.get(f"/api/v1/operator/accounts/{api.target.id}/profile-history")
        assert denied.status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (
            await http.get(f"/api/v1/operator/accounts/{empty.id}/profile-history")
        ).status_code == HTTPStatus.UNAUTHORIZED
    async with api.uow.sessions() as session:
        inspections = tuple(await session.scalars(select(OperatorAuditRecord)))
        actual = next(row for row in inspections if row.requested_id == empty.id)
        absent = next(row for row in inspections if row.requested_id == missing_id)
        assert actual.outcome == "read"
        assert actual.result_ids == [empty.id]
        assert absent.outcome == "not_found"
        assert absent.result_ids == []
        assert len(inspections) == len((actual, absent))
