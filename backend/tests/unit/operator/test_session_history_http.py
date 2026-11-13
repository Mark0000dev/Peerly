from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.session_history_router import (
    OperatorSessionHistoryHttpServices,
    operator_session_history_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.session_history_store import SessionHistoryStore
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_session_history import read

ROOT = f"/api/v1/operator/accounts/{TARGET}/session-history"


@asynccontextmanager
async def client(store: SessionHistoryStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_session_history_router(OperatorSessionHistoryHttpServices(read(store)))
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


async def test_metadata_is_private_without_tokens_or_inferred_authority() -> None:
    store = SessionHistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT)
    assert response.status_code == HTTPStatus.OK
    row = response.json()["sessions"][0]
    assert set(row) == {"id", "account_id", "issued_at", "expires_at", "revoked_at"}
    assert row["revoked_at"] is None
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert store.audit[-1].action.value == "read_account"


async def test_empty_history_is200_but_missing_real_account_audits_before404() -> None:
    store = SessionHistoryStore()
    store.assign_explicit_operator()
    store.histories[TARGET] = ()
    async with client(store) as http:
        response = await http.get(ROOT)
        assert response.status_code == HTTPStatus.OK
        assert response.json()["sessions"] == []
        assert store.audit[-1].outcome.value == "read"
        missing = await http.get(f"/api/v1/operator/accounts/{uuid4()}/session-history")
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "not_found"


async def test_no_default_operator_or_header_authority_and_cookie_required() -> None:
    store = SessionHistoryStore()
    async with client(store) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(ROOT)).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(ROOT)).status_code == HTTPStatus.UNAUTHORIZED
    assert not store.audit
    assert store.private_queries == 0


@pytest.mark.parametrize(
    "query",
    ["version=2", "case_id=private-input", "role=operator", "limit=500", "cursor=" + "x" * 1025],
)
async def test_closed_history_query_never_accepts_grant_or_unbounded_pagination(query: str) -> None:
    store = SessionHistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-input" not in response.text
    assert store.private_queries == 0
    assert not store.audit


async def test_bad_cursor_is_safe_and_not_a_content_grant() -> None:
    store = SessionHistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?cursor=invalid")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert not store.audit


async def test_audit_failure_and_final_session_expiry_return_no_history() -> None:
    store = SessionHistoryStore()
    store.assign_explicit_operator()
    store.fail_audit = True
    async with client(store) as http:
        denied = await http.get(ROOT)
        assert denied.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert denied.headers["Retry-After"] == "1"
        assert "sessions" not in denied.json()
        store.fail_audit = False
        store.expire_after_audit = True
        expired = await http.get(ROOT)
        assert expired.status_code == HTTPStatus.UNAUTHORIZED
        assert "sessions" not in expired.json()
    assert not store.audit
