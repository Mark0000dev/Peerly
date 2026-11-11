from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.feedback.assessments import SaveFeedback
from studymate.application.feedback.outcomes import SaveStudyOutcome
from studymate.application.feedback.prompts import OfferStudyPromptOnVisit
from studymate.application.feedback.reads import ReadOwnFeedbackContext, ReadOwnStudyOutcome
from studymate.domain.feedback.assessments import CurrentFeedback, FeedbackRemoval, RemovalKind
from studymate.domain.feedback.outcomes import StudyAnswer
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.feedback.router import (
    FeedbackHttpServices,
    feedback_problem,
    feedback_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.feedback.store import Store
from tests.unit.feedback.test_usecases import FP, HASHER, command, review
from tests.unit.identity_store import CREDENTIAL

ORIGIN = "https://feedback.test"
SIGNER = HmacBrowserTokenSigner(b"x" * 32)


def services(store: Store) -> FeedbackHttpServices:
    return FeedbackHttpServices(
        SaveStudyOutcome(store, HASHER, FP),
        ReadOwnStudyOutcome(store, HASHER),
        SaveFeedback(store, HASHER, FP),
        ReadOwnFeedbackContext(store, HASHER),
        OfferStudyPromptOnVisit(store, HASHER, FP),
        SIGNER,
        BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
    )


@asynccontextmanager
async def client(store: Store) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(feedback_router(services(store)))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url=ORIGIN,
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        http.headers.update(
            {
                "Origin": ORIGIN,
                "X-CSRF-Token": await SIGNER.csrf_token(CREDENTIAL),
                "Idempotency-Key": str(uuid4()),
            }
        )
        yield http


def root(store: Store) -> str:
    return f"/api/v1/conversations/{store.source.conversation.id}"


async def test_actual_five_operations_with_explicit_writes_and_original_receipts() -> None:
    store = Store()
    async with client(store) as http:
        first_get = await http.get(root(store) + "/study-outcome")
        assert first_get.json() == {"outcome": None}
        context = await http.get(root(store) + "/feedback")
        assert context.json()["can_submit"] is False
        assert not store.prompts
        assert not store.intents
        prompt = await http.post(root(store) + "/study-prompt-visits", json={})
        assert prompt.json()["outcome"] == "offered"
        http.headers["Idempotency-Key"] = str(uuid4())
        yes = await http.put(
            root(store) + "/study-outcome", json={"answer": "yes", "expected_version": 0}
        )
        assert yes.status_code == HTTPStatus.OK
        assert (await http.get(root(store) + "/study-outcome")).json()["outcome"] == yes.json()
        http.headers["Idempotency-Key"] = str(uuid4())
        body = {
            "again": "no",
            "team_note": "Private own team note",
            "descriptors": ["prepared"],
            "expected_version": 0,
        }
        saved = await http.put(root(store) + "/feedback", json=body)
        replay = await http.put(root(store) + "/feedback", json=body)
        assert replay.json() == saved.json()
        assert saved.status_code == HTTPStatus.OK
        assert saved.json()["team_note"] == "Private own team note"
        assert saved.json()["captured_public_eligibility"] is True
        current = await http.get(root(store) + "/feedback")
        assert current.json()["current"] == saved.json()
        assert current.json()["current_publication"] == "eligible"
        assert current.json()["submission_publication"] == "eligible"
        for response in (first_get, context, prompt, yes, saved, replay, current):
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            for field in ("operator_id", "reason", "secret_digest", "message_id", "storage_key"):
                assert field not in response.text


async def test_current_private_snapshot_and_prospective_eligibility_are_distinct() -> None:
    store = Store()
    source = store.source
    store.source = replace(source, high_message=None)
    await SaveStudyOutcome(store, HASHER, FP)(command(store))
    assessment = await SaveFeedback(store, HASHER, FP)(review(store))
    store.source = source
    async with client(store) as http:
        context = await http.get(root(store) + "/feedback")
        assert context.json()["current_publication"] == "private_only"
        assert context.json()["submission_publication"] == "eligible"
        removal = FeedbackRemoval(
            assessment.id,
            assessment.version,
            uuid4(),
            RemovalKind.ABUSIVE,
            "Private operator reason",
            store.clock,
        )
        store.assessments[assessment.reviewer_id, assessment.partner_id] = CurrentFeedback(
            assessment, removal
        )
        removed = await http.get(root(store) + "/feedback")
        assert removed.json()["current_publication"] == "removed"
        assert removed.json()["submission_publication"] == "removed"
        assert removed.json()["can_submit"] is True
        assert "Private operator reason" not in removed.text
        assert "operator_id" not in removed.text


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("GET", "/study-outcome"),
        ("GET", "/feedback"),
        ("PUT", "/study-outcome"),
        ("PUT", "/feedback"),
        ("POST", "/study-prompt-visits"),
    ],
)
async def test_missing_cookie_never_runs_feedback_logic(method: str, suffix: str) -> None:
    store = Store()
    body = (
        {"answer": "yes", "expected_version": 0}
        if suffix == "/study-outcome"
        else {"again": "yes", "expected_version": 0}
        if suffix == "/feedback"
        else {}
    )
    async with client(store) as http:
        http.cookies.clear()
        response = await http.request(
            method, root(store) + suffix, json=body if method != "GET" else None
        )
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert not store.intents
    assert not store.outcomes


@pytest.mark.parametrize(
    ("suffix", "body"),
    [
        ("/study-outcome", {"answer": "yes", "expected_version": 0}),
        ("/feedback", {"again": "yes", "expected_version": 0}),
        ("/study-prompt-visits", {}),
    ],
)
@pytest.mark.parametrize("fault", ["origin", "csrf", "key"])
async def test_writes_require_existing_browser_guards(
    suffix: str, body: dict[str, str | int], fault: str
) -> None:
    store = Store()
    async with client(store) as http:
        if fault == "origin":
            http.headers["Origin"] = "https://untrusted.test"
        elif fault == "csrf":
            http.headers["X-CSRF-Token"] = "invalid"
        else:
            del http.headers["Idempotency-Key"]
        response = await http.request(
            "POST" if suffix == "/study-prompt-visits" else "PUT", root(store) + suffix, json=body
        )
    assert response.status_code == (
        HTTPStatus.UNPROCESSABLE_ENTITY if fault == "key" else HTTPStatus.FORBIDDEN
    )
    assert not store.intents
    assert not store.prompts


@pytest.mark.parametrize(
    "body",
    [
        {"again": "yes", "expected_version": True},
        {"again": "yes", "expected_version": 0, "actor_id": str(uuid4())},
        {"again": "yes", "expected_version": 0, "publication": "eligible"},
        {"again": "yes", "expected_version": 0, "team_note": "x" * 1001},
        {"again": "yes", "expected_version": 0, "descriptors": ["supportive", "supportive"]},
        {"again": "yes", "expected_version": 0, "team_note": "private\u0000bad"},
    ],
)
async def test_strict_input_rejects_authority_and_private_invalid_values_safely(
    body: dict[str, object],
) -> None:
    store = Store()
    async with client(store) as http:
        response = await http.put(root(store) + "/feedback", json=body)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private" not in response.text
    assert not store.intents


async def test_safe_domain_conflict_unavailability_and_lifecycle_errors() -> None:
    store = Store()
    async with client(store) as http:
        missing_yes = await http.put(
            root(store) + "/feedback", json={"again": "yes", "expected_version": 0}
        )
        assert missing_yes.status_code == HTTPStatus.CONFLICT
        assert missing_yes.json()["code"] == "worked_confirmation_required"
        stale = await http.put(
            root(store) + "/study-outcome", json={"answer": "yes", "expected_version": 1}
        )
        assert stale.status_code == HTTPStatus.CONFLICT
        store.fail_save = True
        unavailable = await http.put(
            root(store) + "/study-outcome", json={"answer": "yes", "expected_version": 0}
        )
        assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert unavailable.headers["Retry-After"] == "1"
        store.fail_save = False
        store.access = None
        missing = await http.get(root(store) + "/feedback")
        assert missing.status_code == HTTPStatus.NOT_FOUND
        store.actor = replace(store.actor, banned=True)
        banned = await http.get(root(store) + "/study-outcome")
        assert banned.status_code == HTTPStatus.FORBIDDEN
    with pytest.raises(RuntimeError, match="unexpected"):
        feedback_problem(RuntimeError("unexpected"))


async def test_later_notyet_disables_new_submission_without_retracting_prior_assessment() -> None:
    store = Store()
    await SaveStudyOutcome(store, HASHER, FP)(command(store))
    await SaveFeedback(store, HASHER, FP)(review(store))
    await SaveStudyOutcome(store, HASHER, FP)(command(store, version=1, answer=StudyAnswer.NOT_YET))
    before = store.intents.copy()
    async with client(store) as http:
        context = await http.get(root(store) + "/feedback")
    assert context.json()["can_submit"] is False
    assert context.json()["submission_publication"] is None
    assert context.json()["current_publication"] == "eligible"
    assert store.intents == before
