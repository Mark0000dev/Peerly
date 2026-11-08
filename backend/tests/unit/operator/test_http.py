from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from studymate.application.operator.accounts import ReadOperatorAccount, SearchOperatorAccounts
from studymate.application.operator.messages import ReadOperatorConversationMessages
from studymate.domain.messaging import ConfirmedMessage, MessageContent
from studymate.infrastructure.operator.cursors import FernetOperatorCursorCodec
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.models import AccountSearchQuery, OperatorAccountResponse
from studymate.presentation.operator.router import (
    OperatorHttpServices,
    operator_problem,
    operator_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.store import TARGET, Store

HASHER = Sha256SessionHasher()
CODEC = FernetOperatorCursorCodec.from_key(b"x" * 32)
ROOT = "/api/v1/operator"


def app_for(services: OperatorHttpServices) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(operator_router(services))
    return app


def services(store: Store) -> OperatorHttpServices:
    return OperatorHttpServices(
        SearchOperatorAccounts(store, HASHER, HmacIntentFingerprinter(b"x" * 32), CODEC),
        ReadOperatorAccount(store, HASHER),
        ReadOperatorConversationMessages(store, HASHER, CODEC),
    )


@asynccontextmanager
async def client(store: Store) -> AsyncIterator[AsyncClient]:
    app = app_for(services(store))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://operator.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        yield http


async def test_three_reads_are_private_and_preserve_exact_stored_content() -> None:
    store = Store()
    store.assign_explicit_operator()
    message = ConfirmedMessage(
        uuid4(),
        uuid4(),
        store.conversation.id,
        store.conversation.pair,
        store.conversation.pair.low,
        uuid4(),
        1,
        MessageContent("private stored text"),
        NOW,
    )
    store.messages = (message,)
    store.conversation = replace(store.conversation, next_message_sequence=2)
    async with client(store) as http:
        listing = await http.get(ROOT + "/accounts")
        detail = await http.get(f"{ROOT}/accounts/{TARGET}")
        messages = await http.get(f"{ROOT}/conversations/{store.conversation.id}/messages")
    for response in (listing, detail, messages):
        assert response.status_code == HTTPStatus.OK
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        for forbidden in ("secret_digest", "storage_key", "signed_url", "csrf_token"):
            assert forbidden not in response.text
    assert detail.json()["account"]["display_name"] == "Private original name"
    assert messages.json()["messages"][0]["text"] == "private stored text"
    assert len(store.audit) == len((listing, detail, messages))


@pytest.mark.parametrize(
    "path", ["/accounts", f"/accounts/{TARGET}", f"/conversations/{uuid4()}/messages"]
)
async def test_no_cookie_or_explicit_role_means_no_private_queries(path: str) -> None:
    store = Store()
    async with client(store) as http:
        denied = await http.get(ROOT + path)
        assert denied.status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        absent = await http.get(ROOT + path)
        assert absent.status_code == HTTPStatus.UNAUTHORIZED
        http.cookies.set(SESSION_COOKIE, "malformed")
        invalid = await http.get(ROOT + path)
        assert invalid.status_code == HTTPStatus.UNAUTHORIZED
    assert store.private_queries == 0
    assert not store.audit


async def test_missing_resources_commit_not_found_audits_before404() -> None:
    store = Store()
    store.assign_explicit_operator()
    async with client(store) as http:
        for path in (f"/accounts/{uuid4()}", f"/conversations/{uuid4()}/messages"):
            response = await http.get(ROOT + path)
            assert response.status_code == HTTPStatus.NOT_FOUND
            assert store.audit[-1].outcome.value == "not_found"
    assert len(store.audit) == len(("account", "conversation"))


@pytest.mark.parametrize(
    "query",
    [
        "role=operator",
        "name=" + "s" * 51,
        "google_subject=",
        "google_issuer=https://untrusted.test",
        "institutional_email=private@example.test",
        "created_from=2026-01-01T00:00:00",
        "created_from=2026-02-01T00:00:00Z&created_before=2026-01-01T00:00:00Z",
        "cursor=" + "x" * 1025,
    ],
)
async def test_invalid_filters_fail_safely_without_private_query(query: str) -> None:
    store = Store()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "/accounts?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private@example.test" not in response.text
    assert store.private_queries == 0


async def test_cursor_and_storage_errors_are_safe_not_success() -> None:
    store = Store()
    store.assign_explicit_operator()
    async with client(store) as http:
        invalid = await http.get(ROOT + "/accounts?cursor=not-a-cursor")
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        store.fail_audit = True
        unavailable = await http.get(f"{ROOT}/accounts/{TARGET}")
        assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert unavailable.headers["Retry-After"] == "1"
    assert not store.audit


async def test_expired_session_never_returns_content() -> None:
    store = Store()
    store.assign_explicit_operator()
    store.clock = store.actor.session.expires_at
    async with client(store) as http:
        response = await http.get(f"{ROOT}/accounts/{TARGET}")
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert "Private original name" not in response.text


def test_closed_models_and_unknown_error_are_not_silently_accepted() -> None:
    with pytest.raises(ValidationError):
        AccountSearchQuery.model_validate({"role": "operator"})
    with pytest.raises(ValidationError):
        OperatorAccountResponse.model_validate({"secret_digest": "private"})
    with pytest.raises(RuntimeError, match="unexpected"):
        operator_problem(RuntimeError("unexpected"))
