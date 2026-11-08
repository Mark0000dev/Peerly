from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.operator.goals import OperatorGoalHistoryPage
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.goal_models import goal_history_response
from studymate.presentation.operator.goal_router import (
    OperatorGoalHttpServices,
    operator_goal_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.goal_store import (
    ACTIVE_GOAL,
    RAW_CONTEXT,
    RAW_KEY,
    RAW_LABEL,
    RAW_TOPIC,
    GoalStore,
    revision,
    root,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_goals import history, roots

ROOT = f"/api/v1/operator/accounts/{TARGET}/goals"
HISTORY = f"{ROOT}/{ACTIVE_GOAL}/history"


@asynccontextmanager
async def client(store: GoalStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(operator_goal_router(OperatorGoalHttpServices(roots(store), history(store))))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://operator.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        yield http


async def test_goal_metadata_and_full_raw_history_are_distinct_audited_views() -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        listing = await http.get(ROOT)
        detail = await http.get(HISTORY)
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert listing.json()["pagination"] == "anchored_search_not_commit_order"
    assert "topic" not in listing.json()["goals"][0]
    actual = detail.json()["revisions"][0]
    assert actual["subject_label"] == RAW_LABEL
    assert actual["topic"] == RAW_TOPIC
    assert actual["topic_match_key"] == RAW_KEY
    assert actual["context"] == RAW_CONTEXT
    for response in (listing, detail):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        for forbidden in (
            "secret_digest",
            "storage_key",
            "signed_url",
            "case_id",
            "query_fingerprint",
        ):
            assert forbidden not in response.json()
    assert len(store.audit) == len((listing, detail))


async def test_goal_child404_records_parent_read_and_missing_account_records_not_found() -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        missing_child = await http.get(f"{ROOT}/{uuid4()}/history")
        assert missing_child.status_code == HTTPStatus.NOT_FOUND
        inspected = store.audit[-1]
        assert inspected.outcome.value == "read"
        assert inspected.results[0].id == TARGET
        missing_account = await http.get(f"/api/v1/operator/accounts/{uuid4()}/goals")
        assert missing_account.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "not_found"
        assert not store.audit[-1].results
        store.roots = {}
        empty = await http.get(ROOT)
        assert empty.status_code == HTTPStatus.OK
        assert empty.json()["goals"] == []
        assert empty.json()["anchor_goal_id"] is None


@pytest.mark.parametrize("path", [ROOT, HISTORY])
async def test_goal_inspection_no_header_role_and_requires_cookie(path: str) -> None:
    store = GoalStore()
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
        "topic=private-input",
        "state=unknown",
        "created_from=2026-01-01T00:00:00",
        "created_from=2026-02-01T00:00:00Z&created_before=2026-01-01T00:00:00Z",
        "cursor=" + "x" * 1025,
    ],
)
async def test_goal_root_query_is_closed_bounded_and_sanitized(query: str) -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-input" not in response.text
    assert store.private_queries == 0


@pytest.mark.parametrize("path", [ROOT, HISTORY])
async def test_goal_cursor_is_not_authority_and_storage_failure_returns_no_source_data(
    path: str,
) -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        invalid = await http.get(path + "?cursor=invalid")
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert not store.audit
        store.fail_audit = True
        failure = await http.get(path)
        assert failure.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert failure.headers["Retry-After"] == "1"
        assert "goals" not in failure.json()
        assert "revisions" not in failure.json()
    assert not store.audit


@pytest.mark.parametrize("path", [ROOT, HISTORY])
async def test_goal_final_session_expiry_after_audit_never_returns_private_data(path: str) -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    store.expire_after_audit = True
    async with client(store) as http:
        response = await http.get(path)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert "revisions" not in response.json()
    assert not store.audit


async def test_goal_history_has_no_client_role_filter_limit_or_current_version_override() -> None:
    store = GoalStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        for key, value in (
            ("state", "active"),
            ("limit", "500"),
            ("role", "operator"),
            ("version", "1"),
        ):
            response = await http.get(HISTORY, params={key: value})
            assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert store.private_queries == 0


def test_goal_history_response_does_not_rebuild_goal_content_or_studygoal_policy() -> None:
    raw = replace(
        revision(1),
        subject_label=" ",
        topic="x" * 200,
        context="c" * 500,
        topic_match_key=" UNNORMALIZED ß ",
    )
    page = goal_history_response(OperatorGoalHistoryPage(root(), (raw,), None, 1, NOW))
    assert page.revisions[0].subject_label == " "
    assert page.revisions[0].context == "c" * 500
    assert page.revisions[0].topic_match_key == " UNNORMALIZED ß "
    assert "c" * 500 not in repr(page)
