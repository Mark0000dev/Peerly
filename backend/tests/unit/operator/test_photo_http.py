from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.photo_router import (
    OperatorPhotoHttpServices,
    operator_photo_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.photo_store import (
    FIRST_UPLOAD,
    PhotoStore,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_photo_uploads import history, roots

ROOT = f"/api/v1/operator/accounts/{TARGET}/photo-uploads"
HISTORY = f"{ROOT}/{FIRST_UPLOAD}/history"


@asynccontextmanager
async def client(store: PhotoStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_photo_router(OperatorPhotoHttpServices(roots(store), history(store)))
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


async def test_photo_metadata_and_full_raw_history_are_distinct_audited_views() -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        listing = await http.get(ROOT)
        detail = await http.get(HISTORY)
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert listing.json()["pagination"] == "anchored_search_not_commit_order"
    assert listing.json()["uploads"][0]["source_metadata"] == "declared_not_object_verified"
    assert detail.json()["attempt_observation"] == "current_recorded_not_revision_time"
    assert detail.json()["attempts_current"] == []
    assert detail.json()["origins"] == []
    assert detail.json()["latest_published_photo_ref"] is None
    assert detail.json()["upload"]["source_sha256"] == bytes(range(32)).hex()
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


async def test_photo_child404_records_parent_read_and_missing_account_records_not_found() -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        missing_child = await http.get(f"{ROOT}/{uuid4()}/history")
        assert missing_child.status_code == HTTPStatus.NOT_FOUND
        inspected = store.audit[-1]
        assert inspected.outcome.value == "read"
        assert inspected.results[0].id == TARGET
        missing_account = await http.get(f"/api/v1/operator/accounts/{uuid4()}/photo-uploads")
        assert missing_account.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "not_found"
        assert not store.audit[-1].results
        store.roots = {}
        empty = await http.get(ROOT)
        assert empty.status_code == HTTPStatus.OK
        assert empty.json()["uploads"] == []
        assert empty.json()["anchor_upload_id"] is None


@pytest.mark.parametrize("path", [ROOT, HISTORY])
async def test_photo_inspection_no_header_role_and_requires_cookie(path: str) -> None:
    store = PhotoStore()
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
async def test_photo_root_query_is_closed_bounded_and_sanitized(query: str) -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-input" not in response.text
    assert store.private_queries == 0


@pytest.mark.parametrize("path", [ROOT, HISTORY])
async def test_photo_cursor_is_not_authority_and_storage_failure_returns_no_source_data(
    path: str,
) -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        invalid = await http.get(path + "?cursor=invalid")
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert not store.audit
        store.fail_audit = True
        failure = await http.get(path)
        assert failure.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert failure.headers["Retry-After"] == "1"
        assert "photos" not in failure.json()
        assert "revisions" not in failure.json()
    assert not store.audit


@pytest.mark.parametrize("path", [ROOT, HISTORY])
async def test_photo_final_session_expiry_after_audit_never_returns_private_data(path: str) -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    store.expire_after_audit = True
    async with client(store) as http:
        response = await http.get(path)
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert "revisions" not in response.json()
    assert not store.audit


async def test_photo_history_has_no_client_role_filter_limit_or_current_version_override() -> None:
    store = PhotoStore()
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
