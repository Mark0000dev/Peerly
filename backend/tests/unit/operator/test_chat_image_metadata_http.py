from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.chat_image_router import (
    OperatorChatImageHttpServices,
    operator_chat_image_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.chat_image_store import DIGEST, FIRST_UPLOAD, ChatImageStore
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_chat_image_metadata import attempt, history, operation, roots

ROOT = f"/api/v1/operator/accounts/{TARGET}/chat-image-uploads"
HISTORY = f"{ROOT}/{FIRST_UPLOAD}/history"


@asynccontextmanager
async def client(store: ChatImageStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_chat_image_router(OperatorChatImageHttpServices(roots(store), history(store)))
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


async def test_private_metadata_raw_history_and_matching_client_is_not_attachment_proof() -> None:
    store = ChatImageStore()
    store.assign_explicit_operator()
    store.attempt_rows = (attempt(),)
    store.operation = operation()
    async with client(store) as http:
        listing = await http.get(
            ROOT, params={"conversation_id": str(store.operation.conversation_id)}
        )
        detail = await http.get(HISTORY)
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    body = detail.json()
    assert body["upload"]["source_sha256"] == DIGEST.hex()
    assert body["upload"]["source_metadata"] == "declared_not_object_verified"
    assert body["upload"]["conversation_id"] == str(store.operation.conversation_id)
    assert body["attempts_current"][0]["display_sha256"] == DIGEST.hex()
    assert body["matching_client_operation"]["id"] == str(store.operation.id)
    assert body["operation_observation"] == "current_matching_client_id_no_attachment_proof"
    assert body["attempt_observation"] == "current_recorded_not_revision_time"
    assert body["root_observation"] == "current_recorded_not_revision_time"
    assert body["revisions"][0]["version"] == store.roots[FIRST_UPLOAD].current_version
    for response in (listing, detail):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        for forbidden in (
            "storage_key",
            "upload_url",
            "ticket",
            "lease_token",
            "intent_key",
            "published",
            "origin",
            "message_text",
        ):
            assert forbidden not in response.text
    assert DIGEST.hex() not in repr(store.roots[FIRST_UPLOAD])


@pytest.mark.parametrize("path", [ROOT, HISTORY])
async def test_actual_grant_only_cookie_neutral404_and_no_post(path: str) -> None:
    store = ChatImageStore()
    async with client(store) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(path)).status_code == HTTPStatus.FORBIDDEN
        assert store.private_queries == 0
        http.cookies.clear()
        assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
        http.cookies.set(SESSION_COOKIE, CREDENTIAL.value)
        store.assign_explicit_operator()
        assert (await http.post(path)).status_code == HTTPStatus.METHOD_NOT_ALLOWED
        missing = path.replace(str(TARGET), str(uuid4()))
        assert (await http.get(missing)).status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "not_found"


@pytest.mark.parametrize(
    "query",
    [
        "state=unknown",
        "conversation_id=bad",
        "created_from=2026-01-01T00:00:00",
        "created_from=2026-02-01T00:00:00Z&created_before=2026-01-01T00:00:00Z",
        "cursor=" + "x" * 1025,
        "cursor=bad",
        "role=operator",
        "limit=1",
        "source_url=private-value",
    ],
)
async def test_closed_bounded_root_filters(query: str) -> None:
    store = ChatImageStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-value" not in response.text
    assert not store.audit


@pytest.mark.parametrize("path", [ROOT, HISTORY])
async def test_safe503_and_final_session_expiry_never_release_metadata(path: str) -> None:
    store = ChatImageStore()
    store.assign_explicit_operator()
    store.fail_audit = True
    async with client(store) as http:
        failed = await http.get(path)
        assert failed.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert failed.headers["Retry-After"] == "1"
        assert "source_sha256" not in failed.text
        assert not store.audit
        store.fail_audit = False
        store.expire_after_audit = True
        assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
        assert not store.audit


async def test_history_missing_child_and_rejects_client_current_state_or_storage_grants() -> None:
    store = ChatImageStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        for key in ("state", "conversation_id", "version", "current", "url", "attempt_id"):
            assert (
                await http.get(HISTORY, params={key: "private-value"})
            ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        missing = await http.get(HISTORY.replace(str(FIRST_UPLOAD), str(uuid4())))
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "read"
        assert store.audit[-1].results[0].id == TARGET
        assert (
            await http.get(HISTORY, params={"cursor": "bad"})
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        store.operation = None
        empty = await http.get(HISTORY)
        assert empty.status_code == HTTPStatus.OK
        assert empty.json()["matching_client_operation"] is None
