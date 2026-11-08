from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.ai_router import OperatorAiHttpServices, operator_ai_router
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.ai_store import DIGEST, JOB, RAW_INPUT, RAW_RESULT, AiStore
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_ai_jobs import job, jobs

ROOT = f"/api/v1/operator/accounts/{TARGET}/ai-jobs"
DETAIL = f"{ROOT}/{JOB}"


@asynccontextmanager
async def client(store: AiStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(operator_ai_router(OperatorAiHttpServices(jobs(store), job(store))))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://operator.test",
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        yield http


async def test_list_is_metadata_only_and_detail_preserves_exact_raw_private_strings() -> None:
    store = AiStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        listing = await http.get(ROOT)
        actual = await http.get(DETAIL)
    assert listing.status_code == HTTPStatus.OK
    assert actual.status_code == HTTPStatus.OK
    assert RAW_INPUT not in listing.text
    assert "input_json_raw" not in listing.text
    assert "input_digest_hex" not in listing.text
    assert actual.json()["input_json_raw"] == RAW_INPUT
    assert actual.json()["result_json_raw"] == RAW_RESULT
    assert actual.json()["input_digest_hex"] == DIGEST.hex()
    assert actual.json()["representation"] == "raw_stored_text_not_current_task_schema"
    assert actual.json()["attempt_observation"] == "current_recorded_not_job_snapshot"
    for response in (listing, actual):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        for key in ("token", "generation", "intent_key", "storage_url", "auth_path"):
            assert key not in response.json()


async def test_real_container_audit_on_child404_account404_and_known_empty() -> None:
    store = AiStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        missing = await http.get(f"{ROOT}/{uuid4()}")
        assert missing.status_code == HTTPStatus.NOT_FOUND
        read = store.audit[-1]
        assert read.outcome.value == "read"
        assert read.results[0].id == TARGET
        unknown = await http.get(f"/api/v1/operator/accounts/{uuid4()}/ai-jobs")
        assert unknown.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "not_found"
        store.rows = {}
        empty = await http.get(ROOT)
        assert empty.status_code == HTTPStatus.OK
        assert empty.json()["jobs"] == []


@pytest.mark.parametrize("path", [ROOT, DETAIL])
async def test_no_cookie_or_fake_role_reaches_ai_source(path: str) -> None:
    store = AiStore()
    async with client(store) as http:
        http.headers["X-Operator"] = "true"
        assert (await http.get(path)).status_code == HTTPStatus.FORBIDDEN
        http.cookies.clear()
        assert (await http.get(path)).status_code == HTTPStatus.UNAUTHORIZED
    assert not store.audit
    assert store.private_queries == 0


@pytest.mark.parametrize(
    "query",
    [
        "kind=unknown",
        "state=unknown",
        "created_from=2026-01-01T00:00:00",
        "created_from=2026-02-01T00:00:00Z&created_before=2026-01-01T00:00:00Z",
        "cursor=" + "x" * 1025,
        "prompt=private-prompt",
    ],
)
async def test_metadata_query_closed_bounded_and_safe(query: str) -> None:
    store = AiStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-prompt" not in response.text
    assert not store.audit
    assert store.private_queries == 0


@pytest.mark.parametrize("path", [ROOT, DETAIL])
async def test_final_auth_and_canonical_audit_failure_never_return_data(path: str) -> None:
    store = AiStore()
    store.assign_explicit_operator()
    store.fail_audit = True
    async with client(store) as http:
        failure = await http.get(path)
        assert failure.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert failure.headers["Retry-After"] == "1"
        assert "input_json_raw" not in failure.text
        assert not store.audit
        store.fail_audit = False
        store.expire_after_audit = True
        expired = await http.get(path)
        assert expired.status_code == HTTPStatus.UNAUTHORIZED
        assert not store.audit


async def test_detail_has_no_queue_mutation_or_client_representation_override() -> None:
    store = AiStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        for field in ("role", "kind", "limit", "schema", "source_id", "include_tokens"):
            assert (
                await http.get(DETAIL, params={field: "private-value"})
            ).status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert (await http.post(DETAIL)).status_code == HTTPStatus.METHOD_NOT_ALLOWED
        badcursor = await http.get(ROOT, params={"cursor": "bad"})
        assert badcursor.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert not store.audit
