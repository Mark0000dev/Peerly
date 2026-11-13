from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.operator.timeline import ReadOperatorAudit, ReadOperatorEvent
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.timeline_router import (
    OperatorTimelineHttpServices,
    operator_timeline_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.test_authorized_reads import HASHER
from tests.unit.operator.test_timeline import search
from tests.unit.operator.timeline_store import TimelineStore

ROOT = "/api/v1/operator"


@asynccontextmanager
async def client(store: TimelineStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_timeline_router(
            OperatorTimelineHttpServices(
                search(store), ReadOperatorEvent(store, HASHER), ReadOperatorAudit(store, HASHER)
            )
        )
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://operator.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        yield http


async def test_audited_timeline_returns_actual_metadata_without_private_content() -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    original = store.original_audit()
    async with client(store) as http:
        listing = await http.get(ROOT + "/events")
        detail = await http.get(f"{ROOT}/events/{store.events[0].id}")
        inspection = await http.get(f"{ROOT}/audits/{original.audit.id}")
    assert listing.json()["pagination"] == "anchored_search_not_commit_order"
    assert detail.json()["sources"][0]["id"] == str(store.events[0].sources[0].id)
    assert inspection.json()["operator_access_version"] == original.audit.access.version
    assert inspection.json()["query_fingerprinted"] is False
    for response in (listing, detail, inspection):
        assert response.status_code == HTTPStatus.OK
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        for field in (
            'query_fingerprint"',
            "team_note",
            "message_text",
            "private_prompt",
            "storage_key",
            "secret_digest",
        ):
            assert field not in response.text
    assert len(store.audit) == len((listing, detail, inspection))


@pytest.mark.parametrize(
    "path",
    ["/events", f"/events/{uuid4()}", f"/audits/{uuid4()}"],
    ids=("event-list", "event-detail", "audit-detail"),
)
async def test_read_cookie_and_explicit_role_not_header_claims(path: str) -> None:
    store = TimelineStore()
    async with client(store) as http:
        http.headers["X-Operator"] = "true"
        denied = await http.get(ROOT + path)
        assert denied.status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        missing = await http.get(ROOT + path)
        assert missing.status_code == HTTPStatus.UNAUTHORIZED
    assert store.private_queries == 0
    assert not store.audit


async def test_missing_resources_are_audited_before_http404() -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        for path in (f"/events/{uuid4()}", f"/audits/{uuid4()}"):
            response = await http.get(ROOT + path)
            assert response.status_code == HTTPStatus.NOT_FOUND
            assert store.audit[-1].outcome.value == "not_found"


@pytest.mark.parametrize(
    "query",
    [
        "query=raw-private-search",
        "kind=unknown",
        "trace_id=raw-private-search",
        "trace_id=" + "0" * 32,
        "occurred_from=2026-01-01T00:00:00",
        "occurred_from=2026-02-01T00:00:00Z&occurred_before=2026-01-01T00:00:00Z",
        "cursor=" + "x" * 1025,
    ],
)
async def test_unknown_or_unbounded_query_is_sanitized_before_private_reads(query: str) -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "/events?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "raw-private-search" not in response.text
    assert store.private_queries == 0


@pytest.mark.parametrize(
    "path",
    ["/events", f"/events/{uuid4()}", f"/audits/{uuid4()}"],
    ids=("event-list", "event-detail", "audit-detail"),
)
async def test_failed_audit_never_becomes_data_response(path: str) -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    store.fail_audit = True
    async with client(store) as http:
        response = await http.get(ROOT + path)
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "1"
    assert "sources" not in response.json()
    assert not store.audit


async def test_current_ban_and_invalid_cursor_are_safe() -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        cursor = await http.get(ROOT + "/events?cursor=invalid")
        assert cursor.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        store.actor = replace(store.actor, banned=True)
        denied = await http.get(ROOT + "/events")
        assert denied.status_code == HTTPStatus.FORBIDDEN
