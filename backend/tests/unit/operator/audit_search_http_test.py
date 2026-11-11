"""Closed query/actual metadata DTO HTTP definitions, no root mounting or DB doubles."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.audit_search_router import (
    OperatorAuditSearchHttpServices,
    operator_audit_search_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.audit_search_store import ORIGINAL_OPERATOR, AuditSearchStore, original
from tests.unit.operator.audit_search_usecases_test import search

ROOT = "/api/v1/operator/audits"


@asynccontextmanager
async def client(store: AuditSearchStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(operator_audit_search_router(OperatorAuditSearchHttpServices(search(store))))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://operator.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        yield http


async def test_closed_metadata_response_is_private_and_original_grant_is_not_rebound() -> None:
    store = AuditSearchStore()
    store.assign_explicit_operator()
    store.rows = (original(1),)
    async with client(store) as http:
        response = await http.get(ROOT, params={"operator_id": str(ORIGINAL_OPERATOR)})
    assert response.status_code == HTTPStatus.OK
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    body = response.json()
    detail = body["audits"][0]
    assert detail["operator_id"] == str(ORIGINAL_OPERATOR)
    assert detail["operator_access_version"] == original(1).audit.access.version
    requested = original(1).audit.requested
    assert requested is not None
    assert detail["requested_id"] == str(requested.id)
    assert "query_fingerprint" not in detail
    assert detail["query_fingerprinted"] is False
    assert body["next_cursor"] is None
    assert len(store.audit) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"email": "private-sentinel"},
        {"result_id": "unknown"},
        {"limit": "9999"},
        {"trace_id": "0" * 32},
        {"requested_id": "00000000-0000-0000-0000-000000000001"},
    ],
)
async def test_untyped_private_or_unbounded_query_rejects_before_read(
    params: dict[str, str],
) -> None:
    store = AuditSearchStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT, params=params)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-sentinel" not in response.text
    assert store.private_queries == 0
    assert not store.audit


async def test_role_header_and_missing_cookie_never_authorize_inspection() -> None:
    store = AuditSearchStore()
    async with client(store) as http:
        response = await http.get(ROOT, headers={"X-Operator": "true"})
        assert response.status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(ROOT)).status_code == HTTPStatus.UNAUTHORIZED
    assert store.private_queries == 0


@pytest.mark.parametrize("fail_after", ["audit", "session"])
async def test_failures_never_return_audit_metadata(fail_after: str) -> None:
    store = AuditSearchStore()
    store.assign_explicit_operator()
    store.rows = (original(1),)
    store.fail_audit = fail_after == "audit"
    store.expire_after_audit = fail_after == "session"
    async with client(store) as http:
        response = await http.get(ROOT)
    assert response.status_code == (
        HTTPStatus.SERVICE_UNAVAILABLE if fail_after == "audit" else HTTPStatus.UNAUTHORIZED
    )
    assert "audits" not in response.json()
    assert not store.audit
