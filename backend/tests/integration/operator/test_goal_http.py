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
from studymate.infrastructure.persistence.goal_models import GoalRevisionRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.goal_router import (
    OperatorGoalHttpServices,
    operator_goal_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_goals import (
    RAW_CONTEXT,
    RAW_KEY,
    RAW_LABEL,
    RAW_TOPIC,
    Goals,
    prepared,
)
from tests.integration.student_actor import Actor, actor

pytestmark = pytest.mark.integration


@asynccontextmanager
async def client(api: Goals, viewer: Actor) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-operator-goals")),
    )
    app.include_router(operator_goal_router(OperatorGoalHttpServices(api.roots(), api.history())))
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


async def test_actual_goal_http_raw_history_metadata_and_parent_audit_are_truthful(
    identity_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        await session.execute(
            update(GoalRevisionRecord)
            .where(GoalRevisionRecord.goal_id == api.ended_id, GoalRevisionRecord.version == 1)
            .values(
                subject_label=RAW_LABEL,
                topic=RAW_TOPIC,
                topic_match_key=RAW_KEY,
                context=RAW_CONTEXT,
            )
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
        listing = await http.get(
            f"/api/v1/operator/accounts/{api.target.id}/goals", params={"state": "completed"}
        )
        detail = await http.get(
            f"/api/v1/operator/accounts/{api.target.id}/goals/{api.ended_id}/history"
        )
        child404 = await http.get(
            f"/api/v1/operator/accounts/{api.target.id}/goals/{uuid4()}/history"
        )
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert child404.status_code == HTTPStatus.NOT_FOUND
    assert [row["id"] for row in listing.json()["goals"]] == [str(api.ended_id)]
    assert listing.json()["pagination"] == "anchored_search_not_commit_order"
    assert "topic" not in listing.json()["goals"][0]
    raw = detail.json()["revisions"][-1]
    assert raw["subject_label"] == RAW_LABEL
    assert raw["topic"] == RAW_TOPIC
    assert raw["topic_match_key"] == RAW_KEY
    assert raw["context"] == RAW_CONTEXT
    responses = (listing, detail, child404)
    for response in responses:
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
            assert audit.trace_id == "a" * 32
            assert event.request_id == request_id
            assert event.operator_action == "read_account"
    async with api.uow.sessions() as session:
        assert before is not None
        assert await session.scalar(
            select(func.count()).select_from(ProductEventRecord)
        ) == before + len(responses)
    records = [record for record in caplog.records if record.name == "studymate.http"]
    assert len(records) == len(responses)
    for private in (RAW_LABEL, RAW_TOPIC, RAW_KEY, RAW_CONTEXT):
        assert private not in repr([record.__dict__ for record in records])


async def test_real_goal_http_empty_missing_account_and_explicit_role_boundaries(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    empty = await actor(identity_engine)
    missing = uuid4()
    async with client(api, api.owner) as http:
        known = await http.get(f"/api/v1/operator/accounts/{empty.id}/goals")
        assert known.status_code == HTTPStatus.OK
        assert known.json()["goals"] == []
        unknown = await http.get(f"/api/v1/operator/accounts/{missing}/goals")
        assert unknown.status_code == HTTPStatus.NOT_FOUND
    async with client(api, api.target) as http:
        http.headers["X-Operator"] = "true"
        denied = await http.get(
            f"/api/v1/operator/accounts/{api.target.id}/goals/{api.active_id}/history"
        )
        assert denied.status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (
            await http.get(f"/api/v1/operator/accounts/{empty.id}/goals")
        ).status_code == HTTPStatus.UNAUTHORIZED
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        known_audit = next(row for row in audits if row.requested_id == empty.id)
        unknown_audit = next(row for row in audits if row.requested_id == missing)
        assert known_audit.outcome == "read"
        assert known_audit.result_ids == [empty.id]
        assert unknown_audit.outcome == "not_found"
        assert unknown_audit.result_ids == []
        assert len(audits) == len((known_audit, unknown_audit))
