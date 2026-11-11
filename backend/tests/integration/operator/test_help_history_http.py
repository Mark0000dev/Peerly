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
from studymate.infrastructure.persistence.help_models import HelpSelectionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.help_history_router import (
    OperatorHelpHistoryHttpServices,
    operator_help_history_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_help_history import (
    RAW_KEY,
    RAW_LABEL,
    RAW_NOTE,
    History,
    prepared,
)
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
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-help-history")),
    )
    app.include_router(operator_help_history_router(OperatorHelpHistoryHttpServices(api.read())))
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


async def test_real_help_http_retains_clear_raw_keys_and_account_audit_without_private_telemetry(
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(HelpSelectionRecord)
            .where(
                HelpSelectionRecord.account_id == api.target.id,
                HelpSelectionRecord.version == 1,
                HelpSelectionRecord.subject_id == api.subject_id,
            )
            .values(subject_label=RAW_LABEL, topic_note=RAW_NOTE, topic_match_key=RAW_KEY)
        )
        before = await session.scalar(select(func.count()).select_from(ProductEventRecord))
    action_id = uuid4()
    async with client(api, api.owner) as http:
        http.headers.update(
            {
                "X-Action-ID": str(action_id),
                "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
            }
        )
        response = await http.get(f"/api/v1/operator/accounts/{api.target.id}/help-history")
    assert response.status_code == HTTPStatus.OK, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.json()["account_id"] == str(api.target.id)
    assert [row["version"] for row in response.json()["revisions"]] == [3, 2, 1]
    assert response.json()["revisions"][1]["selections"] == []
    raw = response.json()["revisions"][-1]["selections"][0]
    assert raw["subject_id"] == str(api.subject_id)
    assert raw["subject_label"] == RAW_LABEL
    assert raw["topic_note"] == RAW_NOTE
    assert raw["topic_match_key"] == RAW_KEY
    request_id = UUID(response.headers["X-Request-ID"])
    async with api.uow.sessions() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        ).one()
        assert audit.http_request_id == request_id
        assert audit.action_id == action_id
        assert audit.trace_id == "a" * 32
        assert audit.action == "read_account"
        assert audit.requested_id == api.target.id
        assert audit.result_ids == [api.target.id]
        assert event.operator_audit_id == audit.id
        assert event.request_id == request_id
        assert before is not None
        assert (
            await session.scalar(select(func.count()).select_from(ProductEventRecord)) == before + 1
        )
    records = [record for record in caplog.records if record.name == "studymate.http"]
    assert len(records) == 1
    for private in (RAW_LABEL, RAW_NOTE, RAW_KEY):
        assert private not in repr([record.__dict__ for record in records])


async def test_real_help_history_empty_and_missing_account_audit_and_no_role_fallback(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    empty = await actor(identity_engine)
    async with client(api, api.owner) as http:
        response = await http.get(f"/api/v1/operator/accounts/{empty.id}/help-history")
        assert response.status_code == HTTPStatus.OK
        assert response.json()["revisions"] == []
        assert response.json()["anchor_version"] == 0
        missing_id = uuid4()
        missing = await http.get(f"/api/v1/operator/accounts/{missing_id}/help-history")
        assert missing.status_code == HTTPStatus.NOT_FOUND
    async with client(api, api.target) as http:
        http.headers["X-Operator"] = "true"
        denied = await http.get(f"/api/v1/operator/accounts/{api.target.id}/help-history")
        assert denied.status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (
            await http.get(f"/api/v1/operator/accounts/{empty.id}/help-history")
        ).status_code == HTTPStatus.UNAUTHORIZED
    async with api.uow.sessions() as session:
        rows = tuple(await session.scalars(select(OperatorAuditRecord)))
        actual = next(row for row in rows if row.requested_id == empty.id)
        absent = next(row for row in rows if row.requested_id == missing_id)
        assert actual.outcome == "read"
        assert actual.result_ids == [empty.id]
        assert absent.outcome == "not_found"
        assert absent.result_ids == []
        assert len(rows) == len((actual, absent))
