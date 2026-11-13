from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.request_errors import validation_problem
from studymate.presentation.requests.response_options_router import (
    ResponseOptionsHttpServices,
    response_options_router,
)
from tests.unit.identity_store import CREDENTIAL
from tests.unit.requests.response_options_store import ResponseStore
from tests.unit.requests.test_response_options import read


@asynccontextmanager
async def client(store: ResponseStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(response_options_router(ResponseOptionsHttpServices(read(store))))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://peerly.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        yield http


def route(store: ResponseStore) -> str:
    return f"/api/v1/requests/{store.context.request.id}/response-options"


async def test_exact_tagged_options_headers_and_no_mutation_receipts() -> None:
    store = ResponseStore()
    async with client(store) as http:
        result = await http.get(route(store))
    assert result.status_code == HTTPStatus.OK
    body = result.json()
    assert [option["kind"] for option in body["options"]] == [
        "learning_too",
        "swap",
        "write_my_own",
    ]
    assert body["default_choice"] == "learning_too"
    assert body["request_version"] == store.context.request.version
    assert body["person_id"] == str(store.context.request.context.sender_id)
    assert result.headers["Cache-Control"] == "no-store"
    assert result.headers["Referrer-Policy"] == "no-referrer"
    assert "disclosure_id" not in body
    assert "conversation_id" not in body
    assert "Private synthetic source" not in result.text
    assert "source_digest" not in result.text


async def test_no_cookie_or_unverified_actor_never_reaches_sources() -> None:
    store = ResponseStore()
    async with client(store) as http:
        http.cookies.clear()
        assert (await http.get(route(store))).status_code == HTTPStatus.UNAUTHORIZED
        http.cookies.set(SESSION_COOKIE, CREDENTIAL.value)
        store.actor = replace(store.actor, membership=None)
        assert (await http.get(route(store))).status_code == HTTPStatus.FORBIDDEN
    assert store.source_reads == 0


@pytest.mark.parametrize("query", ["role=operator", "person_id=private", "limit=999", "kind=swap"])
async def test_closed_read_never_takes_client_authority_or_prefill_claims(query: str) -> None:
    store = ResponseStore()
    async with client(store) as http:
        result = await http.get(route(store) + "?" + query)
    assert result.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private" not in result.text
    assert store.source_reads == 0


async def test_unavailable_and_storage_failure_map_to_existing_safe_problems() -> None:
    store = ResponseStore()
    store.unavailable = True
    async with client(store) as http:
        missing = await http.get(route(store))
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert missing.json()["code"] == "request_unavailable"
        store.unavailable = False
        store.storage_failure = True
        failure = await http.get(route(store))
        assert failure.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert failure.headers["Retry-After"] == "1"
        assert "suggested_text" not in failure.text
