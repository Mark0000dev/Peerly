from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.operator.preference_history import OperatorPreferenceHistoryPage
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.preference_history_models import preference_history_response
from studymate.presentation.operator.preference_history_router import (
    OperatorPreferenceHistoryHttpServices,
    operator_preference_history_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.preference_history_store import HistoryStore, revision
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_preference_history import read

ROOT = f"/api/v1/operator/accounts/{TARGET}/notification-preference-history"


@asynccontextmanager
async def client(store: HistoryStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_preference_history_router(OperatorPreferenceHistoryHttpServices(read(store)))
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


async def test_actual_history_is_private_and_raw_without_current_form_photo_or_auth_fields() -> (
    None
):
    store = HistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT)
    assert response.status_code == HTTPStatus.OK
    assert response.json()["revisions"][0]["mode"] == "all_updates"
    assert response.json()["current"] == response.json()["revisions"][0]
    assert set(response.json()["current"]) == {"account_id", "version", "mode", "changed_at"}
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    for forbidden in (
        "photo",
        "display_url",
        "storage_key",
        "secret_digest",
        "case_id",
        "query_fingerprint",
    ):
        assert forbidden not in response.json()
    assert store.audit[-1].requested is not None
    assert store.audit[-1].requested.id == TARGET
    assert store.audit[-1].action.value == "read_account"


async def test_empty_history_is200_but_missing_real_account_audits_before404() -> None:
    store = HistoryStore()
    store.assign_explicit_operator()
    store.histories[TARGET] = ()
    async with client(store) as http:
        response = await http.get(ROOT)
        assert response.status_code == HTTPStatus.OK
        assert response.json()["revisions"] == []
        assert response.json()["current"] is None
        assert store.audit[-1].outcome.value == "read"
        missing = await http.get(
            f"/api/v1/operator/accounts/{uuid4()}/notification-preference-history"
        )
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "not_found"


async def test_no_default_operator_or_header_authority_and_cookie_required() -> None:
    store = HistoryStore()
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
    store = HistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-input" not in response.text
    assert store.private_queries == 0
    assert not store.audit


async def test_bad_cursor_is_safe_and_not_a_content_grant() -> None:
    store = HistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?cursor=invalid")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert not store.audit


async def test_audit_failure_and_final_session_expiry_return_no_history() -> None:
    store = HistoryStore()
    store.assign_explicit_operator()
    store.fail_audit = True
    async with client(store) as http:
        denied = await http.get(ROOT)
        assert denied.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert denied.headers["Retry-After"] == "1"
        assert "revisions" not in denied.json()
        store.fail_audit = False
        store.expire_after_audit = True
        expired = await http.get(ROOT)
        assert expired.status_code == HTTPStatus.UNAUTHORIZED
        assert "revisions" not in expired.json()
    assert not store.audit


def test_history_response_preserves_only_actual_preference_metadata() -> None:
    old = revision(1)
    response = preference_history_response(
        OperatorPreferenceHistoryPage(TARGET, old, (old,), None, 1)
    )
    assert response.current is not None
    assert response.current.mode == old.mode
    assert response.current.changed_at == old.changed_at
    assert set(response.current.model_dump()) == {"account_id", "version", "mode", "changed_at"}
