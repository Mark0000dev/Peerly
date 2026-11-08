from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.feedback_router import (
    OperatorFeedbackHttpServices,
    operator_feedback_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.feedback_store import (
    FEEDBACK,
    RAW_NOTE,
    RAW_REASON,
    FeedbackStore,
    removal,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_peer_feedback import history, removals, roots

ROOT = f"/api/v1/operator/accounts/{TARGET}/peer-feedback"
HISTORY = f"{ROOT}/{FEEDBACK}/history"
REMOVALS = f"{ROOT}/{FEEDBACK}/removals"


@asynccontextmanager
async def client(store: FeedbackStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_feedback_router(
            OperatorFeedbackHttpServices(roots(store), history(store), removals(store))
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


async def test_private_raw_notes_and_removal_reason_never_in_metadata_list() -> None:
    store = FeedbackStore()
    store.assign_explicit_operator()
    store.removals = (removal(),)
    async with client(store) as http:
        listing = await http.get(ROOT)
        detail = await http.get(HISTORY)
        removed = await http.get(REMOVALS)
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert removed.status_code == HTTPStatus.OK
    assert (
        listing.json()["pagination"]
        == "current_pointer_anchored_search_not_creation_or_commit_snapshot"
    )
    assert listing.json()["feedback"][0]["removal_reference"] == "pointer_not_all_history"
    assert "created_at" not in listing.text
    for private in ("team_note", "reason", "descriptors", "again", "fingerprint", "intent_key"):
        assert private not in listing.text
    assert detail.json()["revisions"][0]["team_note"] == RAW_NOTE
    assert detail.json()["revisions"][0]["descriptors"] == ["supportive", "easy_to_communicate"]
    assert removed.json()["removals"][0]["reason"] == RAW_REASON
    assert removed.json()["removals"][0]["source_version"] == 1
    for response in (listing, detail, removed):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "intent_key" not in response.text
        assert "token" not in response.text


@pytest.mark.parametrize("path", [ROOT, HISTORY, REMOVALS])
async def test_actual_db_role_cookie_only_and_no_moderation_http(path: str) -> None:
    store = FeedbackStore()
    async with client(store) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(path)).status_code == HTTPStatus.FORBIDDEN
        assert store.private_queries == 0
        http.cookies.clear()
        assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
        http.cookies.set(SESSION_COOKIE, CREDENTIAL.value)
        store.assign_explicit_operator()
        assert (await http.post(path)).status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert (await http.delete(path)).status_code == HTTPStatus.METHOD_NOT_ALLOWED
        missing = await http.get(path.replace(str(TARGET), str(uuid4())))
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "not_found"


@pytest.mark.parametrize(
    "query",
    [
        "peer_id=bad",
        "direction=both",
        "removed=unknown",
        "changed_from=2026-01-01T00:00:00",
        "changed_from=2026-02-01T00:00:00Z&changed_before=2026-01-01T00:00:00Z",
        "cursor=" + "x" * 1025,
        "cursor=bad",
        "team_note=private-value",
        "role=operator",
        "limit=1",
    ],
)
async def test_closed_bounded_actual_metadata_filters(query: str) -> None:
    store = FeedbackStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-value" not in response.text
    assert not store.audit


@pytest.mark.parametrize("path", [ROOT, HISTORY, REMOVALS])
async def test_canonical_failure503_and_final_expiry_withhold_data(path: str) -> None:
    store = FeedbackStore()
    store.assign_explicit_operator()
    store.fail_audit = True
    async with client(store) as http:
        response = await http.get(path)
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.headers["Retry-After"] == "1"
        assert RAW_NOTE not in response.text
        assert RAW_REASON not in response.text
        assert not store.audit
        store.fail_audit = False
        store.expire_after_audit = True
        assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
        assert not store.audit


@pytest.mark.parametrize("path", [HISTORY, REMOVALS])
async def test_children_closed_cursor_only_and_missing_child_container_audit(path: str) -> None:
    store = FeedbackStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        for key in ("reason", "team_note", "removed", "version", "again", "moderate", "limit"):
            assert (
                await http.get(path, params={key: "private-value"})
            ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (
            await http.get(path, params={"cursor": "bad"})
        ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        missing = await http.get(path.replace(str(FEEDBACK), str(uuid4())))
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "read"
        assert store.audit[-1].results[0].id == TARGET
