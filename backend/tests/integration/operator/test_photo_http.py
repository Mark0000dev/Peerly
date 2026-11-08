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
from studymate.presentation.operator.photo_router import (
    OperatorPhotoHttpServices,
    operator_photo_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_photo_uploads import DIGEST, Photos, prepared
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration


@asynccontextmanager
async def client(api: Photos, viewer: Actor) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-operator-profile-media")),
    )
    app.include_router(operator_photo_router(OperatorPhotoHttpServices(api.roots(), api.history())))
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


async def test_actual_photo_metadata_http_private_response_and_origin_audit(
    identity_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    api = await prepared(identity_engine)
    path = f"/api/v1/operator/accounts/{api.target.id}/photo-uploads"
    action_id = uuid4()
    async with client(api, api.owner) as http:
        http.headers["X-Action-ID"] = str(action_id)
        listing = await http.get(path)
        detail = await http.get(f"{path}/{api.upload_id}/history")
        missing = await http.get(f"{path}/{uuid4()}/history")
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert missing.status_code == HTTPStatus.NOT_FOUND
    assert listing.json()["uploads"][0]["source_sha256"] == DIGEST.hex()
    assert detail.json()["origins"] == []
    assert detail.json()["attempt_observation"] == "current_recorded_not_revision_time"
    assert detail.json()["latest_published_photo_ref"] is None
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
            assert audit.action == "read_account"
            assert audit.outcome == "read"
            assert audit.requested_id == api.target.id
            assert audit.result_ids == [api.target.id]
            assert audit.action_id == action_id
            assert event.request_id == request_id
            assert event.operator_action == "read_account"
        for forbidden in (
            "storage_key",
            "signed_url",
            "upload_ticket",
            "object_exists",
            "secret_digest",
        ):
            assert forbidden not in response.text
    records = [row for row in caplog.records if row.name == "studymate.http"]
    assert len(records) == len((listing, detail, missing))
    assert DIGEST.hex() not in repr([row.__dict__ for row in records])
    assert repr(DIGEST) not in repr([row.__dict__ for row in records])


async def test_actual_http_empty_missing_account_and_explicit_operator_only(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    empty = await actor(identity_engine)
    unknown = uuid4()
    async with client(api, api.owner) as http:
        known = await http.get(f"/api/v1/operator/accounts/{empty.id}/photo-uploads")
        missing = await http.get(f"/api/v1/operator/accounts/{unknown}/photo-uploads")
    assert known.status_code == HTTPStatus.OK
    assert known.json()["uploads"] == []
    assert missing.status_code == HTTPStatus.NOT_FOUND
    async with client(api, api.target) as http:
        http.headers["X-Operator"] = "true"
        response = await http.get(
            f"/api/v1/operator/accounts/{api.target.id}/photo-uploads/{api.upload_id}/history"
        )
        assert response.status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (
            await http.get(f"/api/v1/operator/accounts/{empty.id}/photo-uploads")
        ).status_code == HTTPStatus.UNAUTHORIZED
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == len((known, missing))
        account404 = next(row for row in audits if row.requested_id == unknown)
        assert account404.outcome == "not_found"
        assert account404.result_ids == []
