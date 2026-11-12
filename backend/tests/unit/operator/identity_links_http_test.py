from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.identity_links_router import (
    OperatorIdentityLinksHttpServices,
    operator_identity_links_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.identity_links_store import LinksStore
from tests.unit.operator.identity_links_test import reader
from tests.unit.operator.store import TARGET

ROOT = f"/api/v1/operator/accounts/{TARGET}/identity-links"


@asynccontextmanager
async def client(store: LinksStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_identity_links_router(OperatorIdentityLinksHttpServices(reader(store)))
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


async def test_actual_retirement_facts_are_private_without_auth_material() -> None:
    store = LinksStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT)
    assert response.status_code == HTTPStatus.OK
    assert response.json()["target"]["google"]["subject"] == "private-shared-subject"
    assert response.json()["target"]["google"]["retired_at"] is not None
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "secret_digest" not in response.text
    assert "challenge" not in response.text
    assert "query_fingerprint" not in response.text


async def test_no_default_operator_or_header_authority_and_cookie_required() -> None:
    store = LinksStore()
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
    store = LinksStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-input" not in response.text
    assert store.private_queries == 0
    assert not store.audit


async def test_bad_cursor_is_safe_and_not_a_content_grant() -> None:
    store = LinksStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?cursor=invalid")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert not store.audit
