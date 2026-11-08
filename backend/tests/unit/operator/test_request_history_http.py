from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.request_router import (
    OperatorRequestHttpServices,
    operator_request_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.request_store import (
    RAW_NOTE,
    RAW_SOURCE,
    RAW_TEXT,
    REQUEST,
    RequestStore,
    ack,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_connection_requests import history, requests

ROOT = f"/api/v1/operator/accounts/{TARGET}/connection-requests"
HISTORY = f"{ROOT}/{REQUEST}/history"


@asynccontextmanager
async def client(store: RequestStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_request_router(OperatorRequestHttpServices(requests(store), history(store)))
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


async def test_metadata_only_and_raw_history_with_page_linked_acks_are_private() -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    actual_ack = ack(3)
    store.acknowledgements = (actual_ack,)
    async with client(store) as http:
        listing = await http.get(ROOT)
        detail = await http.get(HISTORY)
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert "request_text" not in listing.text
    assert "source_json_raw" not in listing.text
    assert detail.json()["request_text"] == RAW_TEXT
    assert detail.json()["note"] == RAW_NOTE
    assert detail.json()["preview"]["source_json_raw"] == RAW_SOURCE
    assert detail.json()["request"]["origin"]["trace_id"] == "legacy-trace"
    assert detail.json()["request"]["origin"]["http_request_id"] is None
    assert detail.json()["ack_scope"] == "page_revisions_only"
    assert detail.json()["disclosure_scope"] == "ack_linked_disclosures_not_all_views"
    assert detail.json()["acknowledgements"][0]["disclosure"]["id"] == str(actual_ack.disclosure.id)
    for response in (listing, detail):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "intent_key" not in response.text
        assert "fingerprint" not in response.text
        assert "not_viewed" not in response.text


async def test_child404_parent404_and_empty_account_keep_truthful_container_audit() -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        child = await http.get(f"{ROOT}/{uuid4()}/history")
        assert child.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "read"
        assert store.audit[-1].results[0].id == TARGET
        missing = await http.get(f"/api/v1/operator/accounts/{uuid4()}/connection-requests")
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "not_found"
        store.snapshots = {}
        empty = await http.get(ROOT)
        assert empty.status_code == HTTPStatus.OK
        assert empty.json()["requests"] == []


@pytest.mark.parametrize("path", [ROOT, HISTORY])
async def test_no_cookie_or_fake_header_role_reaches_request_data(path: str) -> None:
    store = RequestStore()
    async with client(store) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(path)).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
    assert store.private_queries == 0
    assert not store.audit


@pytest.mark.parametrize(
    "query",
    [
        "mode=unknown",
        "state=unknown",
        "direction=all",
        "peer_id=bad",
        "sent_from=2026-01-01T00:00:00",
        "sent_from=2026-02-01T00:00:00Z&sent_before=2026-01-01T00:00:00Z",
        "cursor=" + "x" * 1025,
        "text=private-filter",
    ],
)
async def test_closed_metadata_filters_are_bounded_and_sanitized(query: str) -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-filter" not in response.text
    assert store.private_queries == 0


@pytest.mark.parametrize("path", [ROOT, HISTORY])
async def test_audit_failure_and_final_session_expiry_never_release_private_data(path: str) -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    store.fail_audit = True
    async with client(store) as http:
        failed = await http.get(path)
        assert failed.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert failed.headers["Retry-After"] == "1"
        assert "request_text" not in failed.text
        assert not store.audit
        store.fail_audit = False
        store.expire_after_audit = True
        expired = await http.get(path)
        assert expired.status_code == HTTPStatus.UNAUTHORIZED
        assert not store.audit


async def test_history_does_not_accept_client_state_policy_or_mark_viewed() -> None:
    store = RequestStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        for field in ("state", "role", "limit", "viewed", "effective", "version"):
            assert (
                await http.get(HISTORY, params={field: "private-value"})
            ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (await http.post(HISTORY)).status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert (
            await http.get(HISTORY, params={"cursor": "bad"})
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (
            await http.get(ROOT, params={"cursor": "bad"})
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert not store.audit
