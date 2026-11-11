from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.operator.chat_media import ReadOperatorChatMedia
from studymate.domain.operator.chat_media import OperatorChatMediaKind
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.chat_media_router import (
    OperatorChatMediaHttpServices,
    operator_chat_media_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.chat_media_store import (
    ATTEMPT,
    IMAGE,
    PRIVATE_BYTES,
    ChatMediaReader,
    ChatMediaStore,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import HASHER

ROOT = f"/api/v1/operator/accounts/{TARGET}/chat-image-uploads/{IMAGE}/attempts/{ATTEMPT}"


@asynccontextmanager
async def client(store: ChatMediaStore, reader: ChatMediaReader) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_chat_media_router(
            OperatorChatMediaHttpServices(ReadOperatorChatMedia(store, HASHER, reader))
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


@pytest.mark.parametrize("kind", list(OperatorChatMediaKind))
async def test_privileged_bytes_are_attachment_only_private_nosniff_and_audited(
    kind: OperatorChatMediaKind,
) -> None:
    store = ChatMediaStore()
    store.assign_explicit_operator()
    reader = ChatMediaReader(store)
    async with client(store, reader) as http:
        response = await http.get(f"{ROOT}/{kind.value}")
    assert response.status_code == HTTPStatus.OK
    assert response.content == PRIVATE_BYTES
    assert response.headers["Content-Length"] == str(len(PRIVATE_BYTES))
    assert response.headers["Content-Type"] == (
        "application/octet-stream" if kind == OperatorChatMediaKind.ORIGINAL else "image/jpeg"
    )
    assert response.headers["Content-Disposition"] == (
        'attachment; filename="chat-original.bin"'
        if kind == OperatorChatMediaKind.ORIGINAL
        else 'attachment; filename="chat-display.jpg"'
    )
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert "Location" not in response.headers
    assert len(store.media_audits) == 1
    assert store.media_audits[0].request.kind == kind


@pytest.mark.parametrize("bad", ["upload", "transport", "unknown"])
async def test_no_transport_or_arbitrary_kind_exposed(bad: str) -> None:
    store = ChatMediaStore()
    store.assign_explicit_operator()
    reader = ChatMediaReader(store)
    async with client(store, reader) as http:
        response = await http.get(f"{ROOT}/{bad}")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert store.private_queries == 0
    assert not reader.references


@pytest.mark.parametrize(
    "query",
    [
        "role=operator",
        "storage_key=private-key",
        "url=https://invalid.test/private",
        "actor_id=private-actor",
    ],
)
async def test_media_query_has_no_client_authority_or_storage_override(query: str) -> None:
    store = ChatMediaStore()
    store.assign_explicit_operator()
    reader = ChatMediaReader(store)
    async with client(store, reader) as http:
        response = await http.get(f"{ROOT}/original?{query}")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-key" not in response.text
    assert "private-actor" not in response.text
    assert not reader.references
    assert not store.media_audits


async def test_no_header_role_or_missing_session_gets_a_blob() -> None:
    store = ChatMediaStore()
    reader = ChatMediaReader(store)
    async with client(store, reader) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(f"{ROOT}/original")).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(f"{ROOT}/display")).status_code == HTTPStatus.UNAUTHORIZED
    assert not reader.references
    assert store.private_queries == 0


@pytest.mark.parametrize("problem", ["source", "blob", "outage", "audit", "commit", "expiry"])
async def test_problem_response_never_contains_bytes_and_no_fake_read_receipt(problem: str) -> None:
    store = ChatMediaStore()
    store.assign_explicit_operator()
    if problem == "source":
        store.source = None
    store.fail_audit = problem == "audit"
    store.fail_commit = problem == "commit"
    store.expire_after_audit = problem == "expiry"
    reader = ChatMediaReader(store, missing=problem == "blob", unavailable=problem == "outage")
    async with client(store, reader) as http:
        response = await http.get(f"{ROOT}/display")
    expected = (
        HTTPStatus.NOT_FOUND
        if problem in ("source", "blob")
        else HTTPStatus.UNAUTHORIZED
        if problem == "expiry"
        else HTTPStatus.SERVICE_UNAVAILABLE
    )
    assert response.status_code == expected
    assert PRIVATE_BYTES not in response.content
    assert response.headers["Cache-Control"] == "no-store"
    if expected == HTTPStatus.SERVICE_UNAVAILABLE:
        assert response.headers["Retry-After"] == "1"
    if problem in ("source", "blob"):
        assert store.media_audits[0].outcome.value == "not_found"
    else:
        assert not store.media_audits
