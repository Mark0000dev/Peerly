from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.report_moderation.history import ReadReportReviewHistory
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.report_moderation.router import (
    ReportModerationHttpServices,
    report_moderation_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.test_authorized_reads import HASHER
from tests.unit.report_moderation.review_test import CODEC, reviewer
from tests.unit.report_moderation.store import REPORT_ID, ReviewStore

ORIGIN = "https://operator.test"
SIGNER = HmacBrowserTokenSigner(b"r" * 32)
ROOT = f"/api/v1/operator/reports/{REPORT_ID}/reviews"


@asynccontextmanager
async def client(store: ReviewStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        report_moderation_router(
            ReportModerationHttpServices(
                reviewer(store),
                ReadReportReviewHistory(store, HASHER, CODEC),
                SIGNER,
                BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
            )
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=ORIGIN,
        cookies={SESSION_COOKIE: CREDENTIAL.value},
    ) as http:
        http.headers.update(
            {
                "Origin": ORIGIN,
                "X-CSRF-Token": await SIGNER.csrf_token(CREDENTIAL),
                "Idempotency-Key": str(uuid4()),
            }
        )
        yield http


async def test_human_decision_receipt_and_history_are_private_and_replay_exact() -> None:
    store = ReviewStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        body = {"expected_version": 0, "action": "dismiss", "reason": "  private reason  "}
        first = await http.post(ROOT, json=body)
        assert first.status_code == HTTPStatus.OK
        assert (await http.post(ROOT, json=body)).json() == first.json()
        assert first.json()["reason"] == "  private reason  "
        assert first.json()["operator_id"] == str(store.actor.session.account_id)
        assert first.headers["Cache-Control"] == "no-store"
        history = await http.get(ROOT)
        assert history.json()["current"] == first.json()
        assert history.headers["Referrer-Policy"] == "no-referrer"
    assert len(store.reviews) == 1
    assert "private reason" not in repr(store.audit)


@pytest.mark.parametrize("guard", ["origin", "csrf", "cookie", "role"])
async def test_no_browser_or_operator_authority_bypass(guard: str) -> None:
    store = ReviewStore()
    if guard != "role":
        store.assign_explicit_operator()
    async with client(store) as http:
        if guard == "origin":
            http.headers["Origin"] = "https://other.invalid"
        elif guard == "csrf":
            http.headers.pop("X-CSRF-Token")
        elif guard == "cookie":
            http.cookies.clear()
        response = await http.post(
            ROOT, json={"expected_version": 0, "action": "dismiss", "reason": "reason"}
        )
    assert response.status_code == (
        HTTPStatus.UNAUTHORIZED if guard == "cookie" else HTTPStatus.FORBIDDEN
    )
    assert not store.reviews
    assert not store.events


@pytest.mark.parametrize(
    "body",
    [
        {"expected_version": 0, "action": "ban", "reason": "reason"},
        {"expected_version": True, "action": "dismiss", "reason": "reason"},
        {"expected_version": 0, "action": "dismiss", "reason": "  \n "},
        {
            "expected_version": 0,
            "action": "dismiss",
            "reason": "reason",
            "operator_id": "private-input",
        },
    ],
)
async def test_closed_reasoned_decisions_never_accept_unapproved_actions_or_authority(
    body: dict[str, object],
) -> None:
    store = ReviewStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.post(ROOT, json=body)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-input" not in response.text
    assert not store.reviews
