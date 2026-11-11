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
from studymate.infrastructure.feedback.models import PeerFeedbackRevisionRecord
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.operator.models import OperatorAuditRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_operator_audit
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.feedback_router import (
    OperatorFeedbackHttpServices,
    operator_feedback_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.integration.operator.test_peer_feedback import (
    RAW_NOTE,
    RAW_REASON,
    Feedback,
    prepared,
    retained_revision,
    seed_removals,
    source_counts,
)
from tests.integration.student_actor import Actor

pytestmark = pytest.mark.integration


@asynccontextmanager
async def client(
    api: Feedback, viewer: Actor, *, failing: bool = False
) -> AsyncIterator[AsyncClient]:
    provider = TracerProvider()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(
        RequestCorrelation,
        observer=JsonHttpObserver(),
        tracing=OtelHttpTracing(provider.get_tracer("synthetic-operator-peer-feedback")),
    )

    async def fail(session: AsyncSession, audit: OperatorAudit) -> None:
        await record_operator_audit(session, audit)
        raise StorageUnavailableError

    services = replace(api, uow=replace(api.uow, recorder=fail)) if failing else api
    app.include_router(
        operator_feedback_router(
            OperatorFeedbackHttpServices(services.roots(), services.history(), services.removals())
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


def paths(api: Feedback) -> tuple[str, ...]:
    root = f"/api/v1/operator/accounts/{api.revision.reviewer_id}/peer-feedback"
    return root, f"{root}/{api.revision.id}/history", f"{root}/{api.revision.id}/removals"


async def test_actual_private_http_both_raw_histories_canonical_origins_and_safe_logs(
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = await prepared(identity_engine)
    async with api.uow.sessions.begin() as session:
        source = await session.get(PeerFeedbackRevisionRecord, (api.revision.id, 1))
        assert source is not None
        session.add(retained_revision(source, 2))
        await seed_removals(session, api, 1)
        before = await source_counts(session)
    caplog.set_level("INFO", logger="studymate.http")
    action_id = uuid4()
    async with client(api, api.owner) as http:
        http.headers["X-Action-ID"] = str(action_id)
        listing, history, removals = [await http.get(path) for path in paths(api)]
    assert listing.status_code == HTTPStatus.OK
    assert history.status_code == HTTPStatus.OK
    assert removals.status_code == HTTPStatus.OK
    assert "created_at" not in listing.text
    assert (
        listing.json()["pagination"]
        == "current_pointer_anchored_search_not_creation_or_commit_snapshot"
    )
    assert history.json()["revisions"][0]["team_note"] == RAW_NOTE
    assert history.json()["revisions"][0]["descriptors"] == ["supportive", "easy_to_communicate"]
    assert history.json()["revisions"][0]["origin"]["trace_id"] == "a" * 32
    assert removals.json()["removals"][0]["reason"] == RAW_REASON
    assert removals.json()["removals"][0]["origin"]["trace_id"] == "c" * 32
    assert removals.json()["feedback"]["current_removal_id"] is None
    assert removals.json()["feedback"]["removal_reference"] == "pointer_not_all_history"
    for forbidden in ("team_note", "reason", "again", "descriptors"):
        assert forbidden not in listing.text
    async with api.uow.sessions() as session:
        assert await source_counts(session) == before
        for response in (listing, history, removals):
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            assert "intent_key" not in response.text
            request_id = UUID(response.headers["X-Request-ID"])
            audit = (
                await session.scalars(
                    select(OperatorAuditRecord).where(
                        OperatorAuditRecord.http_request_id == request_id
                    )
                )
            ).one()
            assert audit.action == "read_account"
            assert audit.requested_id == api.revision.reviewer_id
            assert audit.result_ids == [api.revision.reviewer_id]
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
        RAW_NOTE.strip(),
        RAW_REASON.strip(),
        "Private retained raw team note",
        "Private retained moderation reason",
        "a" * 32,
        "c" * 32,
    ):
        assert private not in logs


async def test_actual_cookie_role_closed_queries_child404_and_no_mutations(
    identity_engine: AsyncEngine,
) -> None:
    api = await prepared(identity_engine)
    async with client(api, api.api.chat.sender) as http:
        http.headers["X-Operator"] = "true"
        for path in paths(api):
            assert (await http.get(path)).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(paths(api)[0])).status_code == HTTPStatus.UNAUTHORIZED
    async with client(api, api.owner) as http:
        assert (
            await http.get(paths(api)[1], params={"moderate": "true"})
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (await http.delete(paths(api)[2])).status_code == HTTPStatus.METHOD_NOT_ALLOWED
        for path in paths(api)[1:]:
            response = await http.get(path.replace(str(api.revision.id), str(uuid4())))
            assert response.status_code == HTTPStatus.NOT_FOUND
    async with api.uow.sessions() as session:
        audits = tuple(await session.scalars(select(OperatorAuditRecord)))
        assert len(audits) == len(paths(api)[1:])
        assert all(
            row.outcome == "read" and row.result_ids == [api.revision.reviewer_id] for row in audits
        )


@pytest.mark.parametrize("kind", ["roots", "history", "removals"])
async def test_actual_canonical_failure503_returns_no_raw_payload(
    kind: str, identity_engine: AsyncEngine
) -> None:
    api = await prepared(identity_engine)
    root, history, removals = paths(api)
    path = root if kind == "roots" else history if kind == "history" else removals
    async with client(api, api.owner, failing=True) as http:
        response = await http.get(path)
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "1"
    assert "team_note" not in response.text
    assert "reason" not in response.text
    async with api.uow.sessions() as session:
        assert not tuple(await session.scalars(select(OperatorAuditRecord)))
        assert not tuple(
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.kind == "operator.inspected")
            )
        )
