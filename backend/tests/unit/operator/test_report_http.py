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

from studymate.application.operator.profile_reports import ReadOperatorProfileReport
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.operator.report_models import (
    OperatorReportContextResponse,
    OperatorReportQuery,
    OperatorReportsResponse,
    report_detail_response,
)
from studymate.presentation.operator.report_router import (
    OperatorReportHttpServices,
    operator_report_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.report_store import ReportStore
from tests.unit.operator.test_authorized_reads import HASHER
from tests.unit.operator.test_report_reads import search

ROOT = "/api/v1/operator/reports"


@asynccontextmanager
async def client(store: ReportStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_report_router(
            OperatorReportHttpServices(search(store), ReadOperatorProfileReport(store, HASHER))
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


async def test_metadata_list_and_full_exact_private_report_detail_are_separate() -> None:
    store = ReportStore()
    store.assign_explicit_operator()
    source = next(iter(store.details_by_report.values()))
    async with client(store) as http:
        listing = await http.get(ROOT)
        detail = await http.get(f"{ROOT}/{source.report.id}")
    assert listing.status_code == HTTPStatus.OK
    assert detail.status_code == HTTPStatus.OK
    assert listing.json()["reports"][0]["has_comment"]
    assert "comment" not in listing.json()["reports"][0]
    assert detail.json()["comment"] == source.comment
    assert detail.json()["context"]["id"] == str(source.context.id)
    assert detail.json()["submission"] is None
    for response in (listing, detail):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        for forbidden in (
            "secret_digest",
            "storage_key",
            "signed_url",
            "case_id",
            "assignee",
            "query_fingerprint",
        ):
            assert forbidden not in response.text
    assert len(store.audit) == len((listing, detail))


@pytest.mark.parametrize("path", [ROOT, f"{ROOT}/{uuid4()}"])
async def test_only_actual_cookie_and_explicit_role_not_headers_authorize_report_read(
    path: str,
) -> None:
    store = ReportStore()
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
        "comment=private-input",
        "case_id=private-input",
        "category=private-input",
        "reporter_id=private-input",
        "submitted_from=2026-01-01T00:00:00",
        "submitted_from=2026-02-01T00:00:00Z&submitted_before=2026-01-01T00:00:00Z",
        "cursor=" + "x" * 1025,
    ],
)
async def test_closed_bounded_report_search_sanitizes_invalid_private_queries(query: str) -> None:
    store = ReportStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.get(ROOT + "?" + query)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-input" not in response.text
    assert store.private_queries == 0
    assert not store.audit


async def test_actual_missing_is_audited_before_safe404_and_invalid_cursor_before_query() -> None:
    store = ReportStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        missing = await http.get(f"{ROOT}/{uuid4()}")
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert store.audit[-1].outcome.value == "not_found"
        queries = store.private_queries
        invalid = await http.get(ROOT + "?cursor=invalid")
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert store.private_queries == queries


@pytest.mark.parametrize("listing", [True, False])
async def test_failed_audit_returns_safe503_retry_after_without_private_response(
    listing: bool,
) -> None:
    store = ReportStore()
    store.assign_explicit_operator()
    store.fail_audit = True
    path = ROOT if listing else f"{ROOT}/{next(iter(store.details_by_report))}"
    async with client(store) as http:
        response = await http.get(path)
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "1"
    assert "comment" not in response.json()
    assert "reports" not in response.json()
    assert not store.audit


async def test_expired_session_during_report_audit_returns_no_content_and_rolls_back() -> None:
    store = ReportStore()
    store.assign_explicit_operator()
    store.expire_after_audit = True
    async with client(store) as http:
        response = await http.get(f"{ROOT}/{next(iter(store.details_by_report))}")
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert "comment" not in response.json()
    assert not store.audit


async def test_actual_optional_submission_and_original_context_fields_map_without_read_grants() -> (
    None
):
    from studymate.domain.operator.profile_reports import OperatorReportSubmission
    from tests.unit.identity_store import NOW

    store = ReportStore()
    source = next(iter(store.details_by_report.values()))
    original = OperatorReportSubmission(
        uuid4(), source.report.id, source.report.reporter_id, NOW, source.context_origin
    )
    response = report_detail_response(replace(source, submission=original))
    assert response.submission is not None
    assert response.submission.event_id == original.event_id
    assert isinstance(response.context, OperatorReportContextResponse)
    assert response.context.photo_version == source.context.snapshot.photo_version
    assert source.comment is not None
    assert source.comment not in repr(response)
    with pytest.raises(ValidationError):
        OperatorReportQuery.model_validate({"status": "resolved"})
    assert OperatorReportsResponse.model_json_schema()["additionalProperties"] is False
