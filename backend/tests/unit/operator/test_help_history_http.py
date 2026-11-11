from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.operator.help_history import OperatorHelpHistoryPage
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.help_history_models import help_history_response
from studymate.presentation.operator.help_history_router import (
    OperatorHelpHistoryHttpServices,
    operator_help_history_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.help_history_store import (
    CLEAR_VERSION,
    RAW_KEY,
    RAW_LABEL,
    RAW_NOTE,
    HelpHistoryStore,
    revision,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_help_history import read

ROOT = f"/api/v1/operator/accounts/{TARGET}/help-history"


@asynccontextmanager
async def client(store: HelpHistoryStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(operator_help_history_router(OperatorHelpHistoryHttpServices(read(store))))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://operator.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        yield http


async def test_actual_history_is_private_and_raw_without_current_form_photo_or_auth_fields() -> (
    None
):
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT)
    assert response.status_code == HTTPStatus.OK
    selection = response.json()["revisions"][0]["selections"][0]
    assert selection["subject_label"] == RAW_LABEL
    assert selection["topic_note"] == RAW_NOTE
    assert selection["topic_match_key"] == RAW_KEY
    assert response.json()["revisions"][1]["selections"] == []
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    for forbidden in (
        "photo",
        "display_url",
        "storage_key",
        "secret_digest",
        "case_id",
        "query_fingerprint",
    ):
        assert forbidden not in response.json()
    assert store.audit[-1].requested is not None
    assert store.audit[-1].requested.id == TARGET
    assert store.audit[-1].action.value == "read_account"


async def test_empty_history_is200_but_missing_real_account_audits_before404() -> None:
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    store.histories[TARGET] = ()
    async with client(store) as http:
        response = await http.get(ROOT)
        assert response.status_code == HTTPStatus.OK
        assert response.json()["revisions"] == []
        assert store.audit[-1].outcome.value == "read"
        missing = await http.get(f"/api/v1/operator/accounts/{uuid4()}/help-history")
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "not_found"


async def test_no_default_operator_or_header_authority_and_cookie_required() -> None:
    store = HelpHistoryStore()
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
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-input" not in response.text
    assert store.private_queries == 0
    assert not store.audit


async def test_bad_cursor_is_safe_and_not_a_content_grant() -> None:
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?cursor=invalid")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert not store.audit


async def test_audit_failure_and_final_session_expiry_return_no_history() -> None:
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    store.fail_audit = True
    async with client(store) as http:
        denied = await http.get(ROOT)
        assert denied.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert denied.headers["Retry-After"] == "1"
        assert "revisions" not in denied.json()
        store.fail_audit = False
        store.expire_after_audit = True
        expired = await http.get(ROOT)
        assert expired.status_code == HTTPStatus.UNAUTHORIZED
        assert "revisions" not in expired.json()
    assert not store.audit


def test_help_response_does_not_reapply_current_catalogue_or_topic_policy() -> None:
    value = revision(1)
    old = replace(
        value,
        selections=(
            replace(
                value.selections[0],
                subject_label=" ",
                topic_note="x" * 200,
                topic_match_key=" UNNORMALIZED ß ",
            ),
        ),
    )
    response = help_history_response(OperatorHelpHistoryPage(TARGET, (old,), None, 1))
    selected = response.revisions[0].selections[0]
    assert selected.subject_label == " "
    assert selected.topic_note == "x" * 200
    assert selected.topic_match_key == " UNNORMALIZED ß "
    assert "x" * 200 not in repr(response)


async def test_saved_clear_has_a_real_revision_in_http_not_missing_history() -> None:
    store = HelpHistoryStore()
    store.assign_explicit_operator()
    store.histories[TARGET] = (revision(CLEAR_VERSION),)
    async with client(store) as http:
        response = await http.get(ROOT)
    assert response.status_code == HTTPStatus.OK
    assert response.json()["anchor_version"] == CLEAR_VERSION
    assert len(response.json()["revisions"]) == 1
    assert response.json()["revisions"][0]["selections"] == []
