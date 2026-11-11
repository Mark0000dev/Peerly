from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.errors import StorageUnavailableError
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.disclosure_router import (
    OperatorDisclosureHttpServices,
    operator_disclosure_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_connection_requests import Requests, prepared
from tests.integration.operator.test_request_disclosures import (
    reader,
    seed_disclosures,
    source_counts,
    uow,
)
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration


@asynccontextmanager
async def client(
    api: Requests, viewer: Actor, *, failing: bool = False
) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-operator-disclosures")),
    )

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    operation = (
        replace(reader(api), unit_of_work=replace(uow(api), recorder=fail))
        if failing
        else reader(api)
    )
    app.include_router(operator_disclosure_router(OperatorDisclosureHttpServices(operation)))
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


def path(api: Requests) -> str:
    return (
        f"/api/v1/operator/accounts/{api.sender.id}"
        f"/connection-requests/{api.request.id}/disclosures"
    )


async def test_actual_http_private_page_provenance_canonical_audit_and_safe_telemetry(
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        ids = await seed_disclosures(session, api, 4)
        before = await source_counts(session)
    caplog.set_level("INFO", logger="studymate.http")
    action_id = uuid4()
    async with client(api, api.owner) as http:
        http.headers["X-Action-ID"] = str(action_id)
        response = await http.get(path(api), params={"stored_version": "1"})
    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert tuple(UUID(row["id"]) for row in body["disclosures"]) == tuple(reversed(ids))
    assert body["ack_scope"] == "CURRENT_ACK_ROWS_FOR_PAGE_ONLY"
    assert body["disclosure_representation"] == "technical_disclosure_not_ack"
    assert body["disclosures"][0]["origin"]["trace_id"] == "legacy-source-trace"
    assert body["disclosures"][0]["origin"]["http_request_id"] is None
    assert body["acknowledgements"][0]["origin"]["span_id"] == "legacy-span"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    request_id = UUID(response.headers["X-Request-ID"])
    async with api.uow.sessions() as session:
        assert await source_counts(session) == before
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.action == "read_account"
        assert audit.requested_id == api.sender.id
        assert audit.result_ids == [api.sender.id]
        assert audit.http_request_id == request_id
        assert audit.action_id == action_id
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.operator_audit_id == audit.id)
            )
        ).one()
        assert event.request_id == request_id
        assert event.operator_action == "read_account"
    logs = repr([row.__dict__ for row in caplog.records if row.name == "studymate.http"])
    for private in (
        "legacy-source-trace",
        "legacy-span",
        "Private original",
        "request_text",
        "source_json",
        "intent_key",
    ):
        assert private not in logs
        assert private not in response.text or private in ("legacy-source-trace", "legacy-span")


async def test_actual_http_student_denied_closed_query_and_no_mutation(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with client(api, api.sender) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(path(api))).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(path(api))).status_code == HTTPStatus.UNAUTHORIZED
    async with client(api, api.owner) as http:
        assert (
            await http.get(path(api), params={"viewed": "true"})
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (await http.post(path(api))).status_code == HTTPStatus.METHOD_NOT_ALLOWED
        missing = await http.get(path(api).replace(str(api.request.id), str(uuid4())))
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert missing.headers["Cache-Control"] == "no-store"
    async with api.uow.sessions() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.outcome == "read"
        assert audit.result_ids == [api.sender.id]
        assert not (await source_counts(session))[0]


async def test_actual_http_canonical_failure_safe503_no_disclosure_data(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        await seed_disclosures(session, api, 1)
    async with client(api, api.owner, failing=True) as http:
        response = await http.get(path(api))
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "1"
    assert "legacy-source-trace" not in response.text
    assert "disclosures" not in response.text
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
