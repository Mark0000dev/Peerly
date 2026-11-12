from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.operator.report_triage import ReadReportTriage
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.operator.report_triage_router import (
    OperatorReportTriageHttpServices,
    operator_report_triage_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.report_triage.store import REPORT_ID, TriageStore
from tests.unit.operator.report_triage.usecases_test import context_reader, enqueuer
from tests.unit.operator.test_authorized_reads import HASHER

ORIGIN = "https://operator.test"
ROOT = f"/api/v1/operator/reports/{REPORT_ID}"
SIGNER = HmacBrowserTokenSigner(b"t" * 32)


@asynccontextmanager
async def client(store: TriageStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_report_triage_router(
            OperatorReportTriageHttpServices(
                context_reader(store),
                enqueuer(store),
                ReadReportTriage(store, HASHER),
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


async def test_no_fake_pending_before_actual_admission_and_private_source_receipt() -> None:
    store = TriageStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        initial = await http.get(ROOT + "/triage")
        assert initial.status_code == HTTPStatus.OK
        assert initial.json()["triage"] is None
        context = await http.get(ROOT + "/triage-source")
        assert context.status_code == HTTPStatus.OK
        assert context.json()["evidence"] == "Exact private selected evidence"
        assert context.headers["Cache-Control"] == "no-store"
        body = {"source_token": context.json()["source_token"]}
        submitted = await http.post(ROOT + "/triage", json=body)
        assert submitted.status_code == HTTPStatus.OK
        assert submitted.json()["state"] == "queued"
        assert submitted.json()["priority"] is None
        assert submitted.json()["rationale"] is None
        assert submitted.headers["Referrer-Policy"] == "no-referrer"
        assert (await http.post(ROOT + "/triage", json=body)).json() == submitted.json()
    assert len(store.jobs) == 1
    assert "Exact private" not in repr(store.audit)


@pytest.mark.parametrize("guard", ["origin", "csrf", "cookie", "role"])
async def test_operator_ai_enqueue_has_no_cookie_or_browser_bypass(guard: str) -> None:
    store = TriageStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        token = (await http.get(ROOT + "/triage-source")).json()["source_token"]
        if guard == "origin":
            http.headers["Origin"] = "https://other.invalid"
        elif guard == "csrf":
            http.headers.pop("X-CSRF-Token")
        elif guard == "cookie":
            http.cookies.clear()
        else:
            store.access = None
        response = await http.post(ROOT + "/triage", json={"source_token": token})
    assert response.status_code == (
        HTTPStatus.UNAUTHORIZED if guard == "cookie" else HTTPStatus.FORBIDDEN
    )
    assert not store.jobs
    assert not store.snapshots


@pytest.mark.parametrize("extra", ["evidence", "priority", "actor_id", "action", "prompt", "model"])
async def test_privileged_input_cannot_supply_prompt_authority_or_moderation_action(
    extra: str,
) -> None:
    store = TriageStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        token = (await http.get(ROOT + "/triage-source")).json()["source_token"]
        response = await http.post(
            ROOT + "/triage", json={"source_token": token, extra: "private-input"}
        )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-input" not in response.text
    assert not store.jobs


async def test_queue_full_returns_unavailable_not_a_fabricated_job() -> None:
    store = TriageStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        token = (await http.get(ROOT + "/triage-source")).json()["source_token"]
        store.queue_full = True
        response = await http.post(ROOT + "/triage", json={"source_token": token})
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "1"
    assert "job_id" not in response.json()
    assert not store.jobs
