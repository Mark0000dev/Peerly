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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from studymate.application.errors import StorageUnavailableError
from studymate.application.operator.timeline import (
    ReadOperatorAudit,
    ReadOperatorEvent,
    SearchOperatorEvents,
)
from studymate.domain.operator.audit import OperatorAudit
from studymate.domain.operator.profile_media import OperatorProfileMediaKind
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.operator.timeline_cursors import FernetOperatorEventCursorCodec
from studymate.infrastructure.operator.timeline_transactions import SqlOperatorTimelineUnitOfWork
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.media_router import (
    OperatorProfileMediaHttpServices,
    operator_profile_media_router,
)
from studymate.presentation.operator.timeline_router import (
    OperatorTimelineHttpServices,
    operator_timeline_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_media_read import PRIVATE_BINARY, Media, prepared
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration


def path(api: Media, kind: str) -> str:
    request = api.request
    return (
        f"/api/v1/operator/accounts/{request.account_id}/photo-uploads/{request.upload_id}"
        f"/attempts/{request.attempt_id}/{kind}"
    )


@asynccontextmanager
async def client(api: Media, viewer: Actor) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-operator-media")),
    )
    app.include_router(operator_profile_media_router(OperatorProfileMediaHttpServices(api.read())))
    uow = SqlOperatorTimelineUnitOfWork(api.uow.sessions, record_operator_audit)
    app.include_router(
        operator_timeline_router(
            OperatorTimelineHttpServices(
                SearchOperatorEvents(
                    uow, HASHER, FINGERPRINTER, FernetOperatorEventCursorCodec.from_key(b"t" * 32)
                ),
                ReadOperatorEvent(uow, HASHER),
                ReadOperatorAudit(uow, HASHER),
            )
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


async def test_actual_http_bytes_audits_and_canonical_origins_have_no_private_telemetry(
    identity_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    api = await prepared(identity_engine)
    caplog.set_level("INFO", logger="studymate.http")
    action_id = uuid4()
    async with client(api, api.owner) as http:
        http.headers["X-Action-ID"] = str(action_id)
        http.headers["traceparent"] = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
        for kind in OperatorProfileMediaKind:
            response = await http.get(path(api, kind.value))
            assert response.status_code == HTTPStatus.OK
            assert response.content == PRIVATE_BINARY
            assert response.headers["Content-Disposition"].startswith("attachment;")
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
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
                assert audit.action == "read_media"
                assert audit.requested_media_kind == kind.value
                assert audit.requested_media_owner_id == api.target.id
                assert audit.actual_source_upload_id == api.request.upload_id
                assert audit.action_id == action_id
                assert audit.trace_id == "a" * 32
                assert event.request_id == request_id
                assert event.operator_action == "read_media"
            original = await http.get(f"/api/v1/operator/audits/{audit.id}")
            assert original.status_code == HTTPStatus.OK
            assert original.json()["requested_kind"] == "profile_media"
            assert original.json()["requested_media_attempt_id"] == str(api.request.attempt_id)
            assert original.json()["requested_media_kind"] == kind.value
            assert original.json()["actual_source_upload_id"] == str(api.request.upload_id)
            assert "sha256" not in original.text
    records = [row for row in caplog.records if row.name == "studymate.http"]
    assert len(records) == len(tuple(OperatorProfileMediaKind)) * 2
    assert PRIVATE_BINARY.decode() not in repr([row.__dict__ for row in records])


async def test_actual_http_role_cookie_and_override_validation_do_not_access_storage(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with client(api, api.target) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(path(api, "original"))).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(path(api, "display"))).status_code == HTTPStatus.UNAUTHORIZED
    async with client(api, api.owner) as http:
        assert (await http.get(path(api, "upload"))).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        invalid = await http.get(path(api, "original"), params={"storage_key": "private-key"})
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "private-key" not in invalid.text
    assert not api.reader.references
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))


async def test_actual_http_missing_object_is_committed_known_source_not_found(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    api.reader.objects.clear()
    async with client(api, api.owner) as http:
        response = await http.get(path(api, "original"))
    assert response.status_code == HTTPStatus.NOT_FOUND
    async with api.uow.sessions() as session:
        audit = (await session.scalars(select(OperatorAuditRecord))).one()
        assert audit.outcome == "not_found"
        assert audit.result_ids == []
        assert audit.actual_source_upload_id == api.request.upload_id
        assert audit.http_request_id == UUID(response.headers["X-Request-ID"])


@pytest.mark.parametrize("cause", ["storage", "canonical"])
async def test_actual_http_outage_and_canonical_failure_return_safe503_without_bytes(
    cause: str, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)
    if cause == "storage":
        api.reader.unavailable = True
    else:

        async def failed(session: AsyncSession, audit: OperatorAudit) -> None:
            await record_operator_audit(session, audit)
            raise StorageUnavailableError

        api = replace(api, uow=replace(api.uow, recorder=failed))
    async with client(api, api.owner) as http:
        response = await http.get(path(api, "display"))
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "1"
    assert PRIVATE_BINARY not in response.content
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert await session.scalar(select(func.count()).select_from(ProductEventRecord)) == 0
