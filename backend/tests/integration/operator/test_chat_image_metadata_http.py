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
from studymate.presentation.operator.chat_image_router import (
    OperatorChatImageHttpServices,
    operator_chat_image_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.chat_images.legacy import seed_legacy_text_outcome
from tests.integration.operator.test_chat_image_metadata import Images, prepared, source_counts
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration


@asynccontextmanager
async def client(
    api: Images, viewer: Actor, *, failing: bool = False
) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-operator-chat-image")),
    )

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    services = replace(api, uow=replace(api.uow, recorder=fail)) if failing else api
    app.include_router(
        operator_chat_image_router(
            OperatorChatImageHttpServices(services.roots(), services.history())
        )
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


def root_path(api: Images) -> str:
    return f"/api/v1/operator/accounts/{api.image.account_id}/chat-image-uploads"


def history_path(api: Images) -> str:
    return f"{root_path(api)}/{api.image.id}/history"


async def test_actual_http_private_metadata_canonical_origin_and_no_telemetry_payload(
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = await prepared(identity_engine)
    text = await seed_legacy_text_outcome(api.chat, api.image)
    async with api.uow.sessions() as session:
        before = await source_counts(session)
    caplog.set_level("INFO", logger="studymate.http")
    action_id = uuid4()
    async with client(api, api.owner) as http:
        http.headers["X-Action-ID"] = str(action_id)
        listing = await http.get(
            root_path(api), params={"conversation_id": str(api.image.conversation_id)}
        )
        detail = await http.get(history_path(api))
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert listing.json()["uploads"][0]["source_sha256"] == api.image.source.sha256.hex()
    body = detail.json()
    assert body["upload"]["client_message_id"] == str(api.image.client_message_id)
    assert body["upload"]["source_metadata"] == "declared_not_object_verified"
    assert body["matching_client_operation"]["id"] == str(text.id)
    assert body["operation_observation"] == "current_matching_client_id_no_attachment_proof"
    assert body["attempts_current"] == []
    async with api.uow.sessions() as session:
        assert await source_counts(session) == before
        for response in (listing, detail):
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            request_id = UUID(response.headers["X-Request-ID"])
            audit = (
                await session.scalars(
                    select(OperatorAuditRecord).where(
                        OperatorAuditRecord.http_request_id == request_id
                    )
                )
            ).one()
            assert audit.action == "read_account"
            assert audit.requested_id == api.image.account_id
            assert audit.result_ids == [api.image.account_id]
            assert audit.action_id == action_id
            event = (
                await session.scalars(
                    select(ProductEventRecord).where(
                        ProductEventRecord.operator_audit_id == audit.id
                    )
                )
            ).one()
            assert event.request_id == request_id
            assert event.operator_action == "read_account"
    logs = repr([row.__dict__ for row in caplog.records if row.name == "studymate.http"])
    for private in (
        api.image.source.sha256.hex(),
        "Synthetic private message",
        "source_sha256",
        "display_sha256",
    ):
        assert private not in logs
    for response in (listing, detail):
        for forbidden in (
            "storage_key",
            "upload_url",
            "lease_token",
            "intent_key",
            "published",
            "Synthetic private message",
            "origin",
        ):
            assert forbidden not in response.text


async def test_actual_http_cookie_role_closed_query_and_missing_child_audit(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with client(api, api.chat.sender) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(root_path(api))).status_code == HTTPStatus.FORBIDDEN
        assert (await http.get(history_path(api))).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(root_path(api))).status_code == HTTPStatus.UNAUTHORIZED
    async with client(api, api.owner) as http:
        assert (
            await http.get(history_path(api), params={"url": "private-value"})
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (await http.post(history_path(api))).status_code == HTTPStatus.METHOD_NOT_ALLOWED
        missing = await http.get(history_path(api).replace(str(api.image.id), str(uuid4())))
        assert missing.status_code == HTTPStatus.NOT_FOUND
    async with api.uow.sessions() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.outcome == "read"
        assert audit.result_ids == [api.image.account_id]


@pytest.mark.parametrize("read_history", [True, False])
async def test_actual_http_canonical_failure_never_returns_private_hashes(
    read_history: bool,
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    path = history_path(api) if read_history else root_path(api)
    async with client(api, api.owner, failing=True) as http:
        response = await http.get(path)
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "1"
    assert api.image.source.sha256.hex() not in response.text
    assert "source_sha256" not in response.text
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
