from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.disclosure_router import (
    OperatorDisclosureHttpServices,
    operator_disclosure_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.disclosure_store import DisclosureStore, linked_ack
from tests.unit.operator.request_store import REQUEST
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_request_disclosures import reader

PATH = f"/api/v1/operator/accounts/{TARGET}/connection-requests/{REQUEST}/disclosures"


@asynccontextmanager
async def client(store: DisclosureStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(operator_disclosure_router(OperatorDisclosureHttpServices(reader(store))))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://operator.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        yield http


async def test_technical_metadata_exact_acks_and_no_private_source_payloads() -> None:
    store = DisclosureStore()
    store.assign_explicit_operator()
    store.acks = (linked_ack(store.rows[0]),)
    async with client(store) as http:
        response = await http.get(PATH, params={"stored_version": "1"})
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["disclosure_representation"] == "technical_disclosure_not_ack"
    assert data["ack_scope"] == "CURRENT_ACK_ROWS_FOR_PAGE_ONLY"
    assert data["pagination"] == "anchored_search_not_commit_order"
    assert data["root_observation"] == "current_recorded_not_revision_snapshot"
    assert data["disclosures"][0]["id"] == str(store.rows[0].id)
    assert data["disclosures"][0]["sender_id"] == str(TARGET)
    assert data["disclosures"][0]["origin"]["trace_id"] == "legacy-source"
    assert data["acknowledgements"][0]["disclosure"]["id"] == str(store.rows[0].id)
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    for forbidden in (
        "request_text",
        "source_json",
        "note",
        "intent_key",
        "fingerprint",
        "not_viewed",
    ):
        assert forbidden not in response.text
    assert store.audit[-1].results[0].id == TARGET


@pytest.mark.parametrize(
    "query",
    [
        "stored_version=0",
        "stored_version=true",
        "stored_version=2147483648",
        "viewer_id=bad",
        "disclosure_id=bad",
        "acknowledgement_id=bad",
        "created_from=2026-01-01T00:00:00",
        "created_from=2026-02-01T00:00:00Z&created_before=2026-01-01T00:00:00Z",
        "cursor=" + "x" * 1025,
        "cursor=broken",
        "viewed=true",
        "limit=1",
        "role=operator",
        "text=private-filter",
    ],
)
async def test_closed_bounded_queries_do_not_add_authority_or_private_filters(query: str) -> None:
    store = DisclosureStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(PATH + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-filter" not in response.text
    assert not store.audit


async def test_auth_neutral404_post_forbidden_and_canonical_failure() -> None:
    store = DisclosureStore()
    async with client(store) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(PATH)).status_code == HTTPStatus.FORBIDDEN
        assert store.private_queries == 0
        http.cookies.clear()
        assert (await http.get(PATH)).status_code == HTTPStatus.UNAUTHORIZED
        http.cookies.set(SESSION_COOKIE, CREDENTIAL.value)
        store.assign_explicit_operator()
        missing = PATH.replace(str(REQUEST), str(uuid4()))
        assert (await http.get(missing)).status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "read"
        assert (await http.post(PATH)).status_code == HTTPStatus.METHOD_NOT_ALLOWED
        store.fail_audit = True
        failed = await http.get(PATH)
        assert failed.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert failed.headers["Retry-After"] == "1"
        assert "disclosures" not in failed.text
        store.fail_audit = False
        store.expire_after_audit = True
        assert (await http.get(PATH)).status_code == HTTPStatus.UNAUTHORIZED
