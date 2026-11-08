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
from studymate.infrastructure.ai.models import AiAttemptRecord
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.ai_router import OperatorAiHttpServices, operator_ai_router
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_ai_jobs import INTENT_KEY, Jobs, prepared
from tests.integration.student_actor import Actor, actor
from tests.unit.operator.ai_store import DIGEST, RAW_INPUT, RAW_RESULT

pytestmark = pytest.mark.integration


@asynccontextmanager
async def client(api: Jobs, viewer: Actor) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-operator-ai-inspection")),
    )
    app.include_router(operator_ai_router(OperatorAiHttpServices(api.jobs(), api.job())))
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


async def test_actual_http_raw_strings_private_digests_and_secret_exclusion_are_audited(
    identity_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    api = await prepared(identity_engine)
    caplog.set_level("INFO", logger="studymate.http")
    path = f"/api/v1/operator/accounts/{api.target.id}/ai-jobs"
    action_id = uuid4()
    async with client(api, api.owner) as http:
        http.headers["X-Action-ID"] = str(action_id)
        listing = await http.get(path, params={"kind": "clarify_goal", "state": "succeeded"})
        detail = await http.get(f"{path}/{api.job_id}")
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert "input_json_raw" not in listing.text
    assert "input_digest_hex" not in listing.text
    assert detail.json()["input_json_raw"] == RAW_INPUT
    assert detail.json()["result_json_raw"] == RAW_RESULT
    assert detail.json()["input_digest_hex"] == DIGEST.hex()
    assert detail.json()["job"]["origin"]["http_request_id"] == str(api.origin_request_id)
    assert detail.json()["representation"] == "raw_stored_text_not_current_task_schema"
    assert len(detail.json()["attempts_current"]) == len((1, 2, 3))
    async with api.uow.sessions() as session:
        tokens = tuple(await session.scalars(select(AiAttemptRecord.token)))
    for response in (listing, detail):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        for secret in (str(api.token), INTENT_KEY, *(str(value) for value in tokens)):
            assert secret not in response.text
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
            assert audit.requested_id == api.target.id
            assert audit.result_ids == [api.target.id]
            assert audit.action_id == action_id
            assert event.request_id == request_id
            assert event.operator_action == "read_account"
    logs = repr([row.__dict__ for row in caplog.records if row.name == "studymate.http"])
    assert "Private retained goal text" not in logs
    assert RAW_RESULT not in logs
    assert DIGEST.hex() not in logs
    assert str(api.token) not in logs


async def test_actual_http_child404_empty_and_role_boundary_never_invent_ai_authority(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    path = f"/api/v1/operator/accounts/{api.target.id}/ai-jobs"
    empty = await actor(identity_engine)
    async with client(api, api.owner) as http:
        child = await http.get(f"{path}/{uuid4()}")
        assert child.status_code == HTTPStatus.NOT_FOUND
        known = await http.get(f"/api/v1/operator/accounts/{empty.id}/ai-jobs")
        assert known.status_code == HTTPStatus.OK
        assert known.json()["jobs"] == []
        invalid = await http.get(f"{path}/{api.job_id}", params={"include_tokens": "true"})
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    async with client(api, api.target) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(f"{path}/{api.job_id}")).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == len((child, known))
        assert all(
            item.outcome == "read" and item.result_ids == [item.requested_id] for item in audits
        )


async def test_actual_http_canonical_failure_returns503_without_retained_body(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    api = replace(api, uow=replace(api.uow, recorder=fail))
    async with client(api, api.owner) as http:
        response = await http.get(f"/api/v1/operator/accounts/{api.target.id}/ai-jobs/{api.job_id}")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "1"
    assert "input_json_raw" not in response.text
    assert RAW_RESULT not in response.text
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(await session.scalars(select(ProductEventRecord)))
