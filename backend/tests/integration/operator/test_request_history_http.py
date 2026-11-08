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
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.errors import StorageUnavailableError
from studymate.domain.operator.audit import OperatorAudit
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.infrastructure.requests.models import ConnectionRequestRecord, RequestPreviewRecord
from studymate.infrastructure.requests.view_models import (
    RequestDisclosureRecord,
    RequestViewAcknowledgementRecord,
)
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.request_router import (
    OperatorRequestHttpServices,
    operator_request_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_connection_requests import (
    RAW_JSON,
    RAW_NOTE,
    RAW_TEXT,
    Requests,
    prepared,
    seed_history,
)
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration


@asynccontextmanager
async def client(api: Requests, viewer: Actor) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-operator-request-history")),
    )
    app.include_router(
        operator_request_router(OperatorRequestHttpServices(api.roots(), api.history()))
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


async def test_actual_private_http_history_source_ack_scopes_and_canonical_origins(
    identity_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(ConnectionRequestRecord)
            .where(ConnectionRequestRecord.id == api.request.id)
            .values(
                request_text=RAW_TEXT,
                note=RAW_NOTE,
                request_id=None,
                action_id=uuid4(),
                trace_id="legacy-not-hex",
                span_id=None,
            )
        )
        await session.execute(
            update(RequestPreviewRecord)
            .where(RequestPreviewRecord.id == api.request.preview_id)
            .values(source_json=RAW_JSON)
        )
        await seed_history(session, api, (1, 3), acks=True)
        before_disclosures = await session.scalar(
            select(func.count()).select_from(RequestDisclosureRecord)
        )
        before_acks = await session.scalar(
            select(func.count()).select_from(RequestViewAcknowledgementRecord)
        )
    caplog.set_level("INFO", logger="studymate.http")
    action_id = uuid4()
    path = f"/api/v1/operator/accounts/{api.sender.id}/connection-requests"
    async with client(api, api.owner) as http:
        http.headers["X-Action-ID"] = str(action_id)
        listing = await http.get(path)
        detail = await http.get(f"{path}/{api.request.id}/history")
        child404 = await http.get(f"{path}/{uuid4()}/history")
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert child404.status_code == HTTPStatus.NOT_FOUND
    assert "request_text" not in listing.text
    assert "source_json_raw" not in listing.text
    body = detail.json()
    assert body["request_text"] == RAW_TEXT
    assert body["note"] == RAW_NOTE
    assert body["preview"]["source_json_raw"] == RAW_JSON
    assert body["request"]["origin"]["trace_id"] == "legacy-not-hex"
    assert body["request"]["origin"]["http_request_id"] is None
    assert body["ack_scope"] == "page_revisions_only"
    assert body["disclosure_scope"] == "ack_linked_disclosures_not_all_views"
    assert len(body["acknowledgements"]) == len((1, 2, 3, 4))
    for response in (listing, detail, child404):
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
            assert audit.action == "read_account"
            assert audit.requested_id == api.sender.id
            assert audit.result_ids == [api.sender.id]
            assert audit.outcome == "read"
            assert audit.action_id == action_id
            assert event.request_id == request_id
            assert event.operator_action == "read_account"
    async with api.uow.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(RequestDisclosureRecord))
            == before_disclosures
        )
        assert (
            await session.scalar(select(func.count()).select_from(RequestViewAcknowledgementRecord))
            == before_acks
        )
    logs = repr([row.__dict__ for row in caplog.records if row.name == "studymate.http"])
    for private in (
        RAW_TEXT.strip(),
        RAW_NOTE.strip(),
        "Private retained academic material",
        "legacy-not-hex",
    ):
        assert private not in logs


async def test_actual_student_denial_and_strict_readonly_query_and_method(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    path = f"/api/v1/operator/accounts/{api.sender.id}/connection-requests"
    async with client(api, api.sender) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(path)).status_code == HTTPStatus.FORBIDDEN
        assert (
            await http.get(f"{path}/{api.request.id}/history")
        ).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
    async with client(api, api.owner) as http:
        invalid = await http.get(f"{path}/{api.request.id}/history", params={"viewed": "true"})
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (
            await http.post(f"{path}/{api.request.id}/history")
        ).status_code == HTTPStatus.METHOD_NOT_ALLOWED
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(await session.scalars(select(RequestDisclosureRecord)))
        assert not tuple(await session.scalars(select(RequestViewAcknowledgementRecord)))


async def test_actual_canonical_failure_returns_safe503_without_private_snapshot(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    api = replace(api, uow=replace(api.uow, recorder=fail))
    async with client(api, api.owner) as http:
        response = await http.get(
            f"/api/v1/operator/accounts/{api.sender.id}/connection-requests/{api.request.id}/history"
        )
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "1"
    assert "source_json_raw" not in response.text
    assert "request_text" not in response.text
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
