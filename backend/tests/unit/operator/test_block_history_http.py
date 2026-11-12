from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.block_history_router import (
    OperatorBlockHistoryHttpServices,
    operator_block_history_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.block_history_store import PAIR, RELATIONSHIP, BlockHistoryStore
from tests.unit.operator.test_block_history import read

ROOT = f"/api/v1/operator/accounts/{PAIR.low}/relationships/{RELATIONSHIP}/block-history"


@asynccontextmanager
async def client(store: BlockHistoryStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(operator_block_history_router(OperatorBlockHistoryHttpServices(read(store))))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://operator.test",
        cookies={SESSION_COOKIE: CREDENTIAL.value},
    ) as http:
        yield http


async def test_private_metadata_never_claims_chat_or_fake_unblocked_source() -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT)
    assert response.status_code == HTTPStatus.OK
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.json()["anchors"] == {"low_version": 2, "high_version": 1}
    assert response.json()["current_heads"][0]["blocker_id"] == str(PAIR.high)
    assert response.json()["current_heads"][0]["target_id"] == str(PAIR.low)
    assert response.json()["current_heads"][0]["blocked"] is True
    assert all(row["version"] > 0 for row in response.json()["revisions"])
    assert "conversation_id" not in response.text
    assert "can_message" not in response.text
    assert store.audit[-1].results[0].id == PAIR.low


async def test_empty_pair_and_missing_child_have_truthful_container_audits() -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    store.rows = ()
    async with client(store) as http:
        empty = await http.get(ROOT)
        assert empty.status_code == HTTPStatus.OK
        assert empty.json()["current_heads"] == []
        assert empty.json()["revisions"] == []
        missing = await http.get(
            f"/api/v1/operator/accounts/{PAIR.low}/relationships/{uuid4()}/block-history"
        )
        assert missing.status_code == HTTPStatus.NOT_FOUND
    assert store.audit[-1].outcome.value == "read"
    assert store.audit[-1].results[0].id == PAIR.low


async def test_no_implicit_header_authority_and_cookie_required() -> None:
    store = BlockHistoryStore()
    async with client(store) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(ROOT)).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(ROOT)).status_code == HTTPStatus.UNAUTHORIZED
    assert not store.audit
    assert store.private_queries == 0


@pytest.mark.parametrize(
    "query", ["limit=500", "role=operator", "blocked=false", "cursor=" + "x" * 1025]
)
async def test_closed_history_query_does_not_accept_state_changes_or_unbounded_reads(
    query: str,
) -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert not store.audit
    assert store.private_queries == 0


async def test_audit_failure_and_final_expiry_return_no_directional_graph() -> None:
    store = BlockHistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        store.fail_audit = True
        failed = await http.get(ROOT)
        assert failed.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert "revisions" not in failed.json()
        store.fail_audit = False
        store.expire_after_audit = True
        expired = await http.get(ROOT)
        assert expired.status_code == HTTPStatus.UNAUTHORIZED
        assert "revisions" not in expired.json()
    assert not store.audit
