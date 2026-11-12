from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.operator.lifecycle_history import OperatorLifecycleHistoryPage
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.lifecycle_history_models import lifecycle_history_response
from studymate.presentation.operator.lifecycle_history_router import (
    OperatorLifecycleHistoryHttpServices,
    operator_lifecycle_history_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.lifecycle_history_store import HistoryStore, revision
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_lifecycle_history import read

ROOT = f"/api/v1/operator/accounts/{TARGET}/lifecycle-history"


@asynccontextmanager
async def client(store: HistoryStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_lifecycle_history_router(OperatorLifecycleHistoryHttpServices(read(store)))
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
    assert response.json()["revisions"][0]["reason"] == "  Private exact reason  "
    assert response.json()["revisions"][0]["operator_access_version"] == 1
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
        assert store.audit[-1].outcome.value == "read"
        missing = await http.get(f"/api/v1/operator/accounts/{uuid4()}/lifecycle-history")
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


def test_history_response_does_not_reapply_current_input_policy() -> None:
    old = replace(revision(1), reason="  exact retained reason  " + "x" * 2000)
    response = lifecycle_history_response(OperatorLifecycleHistoryPage(TARGET, (old,), None, 1))
    assert response.revisions[0].reason == old.reason
    assert "exact retained reason" not in repr(response)
