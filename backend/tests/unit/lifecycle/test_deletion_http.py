from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from http.cookies import SimpleCookie
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.domain.lifecycle.states import AccountLifecycle
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.identity import LOGIN_COOKIE
from studymate.presentation.lifecycle.deletion_router import (
    DeletionHttpServices,
    deletion_problem,
    deletion_router,
)
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.lifecycle.deletion_store import DeletionStore
from tests.unit.lifecycle.test_deletions import delete
from tests.unit.lifecycle.test_states import WORKFLOW

ORIGIN = "https://deletion.test"
HOST = "deletion.test"
SIGNER = HmacBrowserTokenSigner(b"d" * 32)
PATH = "/api/v1/me/deletion"
# Synthetic unrelated cookie ONLY: not a published name or implementation of main recovery proof.
UNRELATED_OUTCOME_COOKIE = "__Host-synthetic_outcome_test"
UNRELATED_OUTCOME_VALUE = "opaque-synthetic-preserved-proof"


def application(store: DeletionStore) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.add_middleware(RequestCorrelation, observer=JsonHttpObserver())
    app.include_router(
        deletion_router(
            DeletionHttpServices(
                delete(store), SIGNER, BrowserConfiguration(ORIGIN, frozenset({ORIGIN}))
            )
        )
    )
    return app


@asynccontextmanager
async def client(store: DeletionStore) -> AsyncIterator[AsyncClient]:
    app = application(store)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as http,
    ):
        http.cookies.set(SESSION_COOKIE, CREDENTIAL.value, domain=HOST, path="/")
        http.cookies.set(LOGIN_COOKIE, "synthetic-login-cookie", domain=HOST, path="/")
        http.cookies.set(UNRELATED_OUTCOME_COOKIE, UNRELATED_OUTCOME_VALUE, domain=HOST, path="/")
        http.headers.update(
            {
                "Origin": ORIGIN,
                "X-CSRF-Token": await SIGNER.csrf_token(CREDENTIAL),
                "Idempotency-Key": str(uuid4()),
            }
        )
        yield http


async def test_actual_commit_receipt_clears_only_existing_session_and_delayed_replay_matches() -> (
    None
):
    store = DeletionStore()
    async with client(store) as http:
        submitted = {"workflow_id": str(WORKFLOW)}
        response = await http.post(PATH, json=submitted)
        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert set(body) == {"workflow_id", "deleted_at", "source_version"}
        assert body["workflow_id"] == str(WORKFLOW)
        assert body["source_version"] == 1
        assert body["deleted_at"] == store.deletion_sources[0].deleted_at.isoformat().replace(
            "+00:00", "Z"
        )
        cookies = response.headers.get_list("Set-Cookie")
        assert len(cookies) == 1
        parsed = SimpleCookie()
        parsed.load(cookies[0])
        assert set(parsed) == {SESSION_COOKIE}
        retired = parsed[SESSION_COOKIE]
        assert retired["path"] == "/"
        assert retired["max-age"] == "0"
        assert retired["secure"]
        assert retired["httponly"]
        assert retired["samesite"].lower() == "lax"
        assert http.cookies.get(SESSION_COOKIE) is None
        assert http.cookies.get(LOGIN_COOKIE) == "synthetic-login-cookie"
        assert http.cookies.get(UNRELATED_OUTCOME_COOKIE) == UNRELATED_OUTCOME_VALUE
        # Represents an already-submitted request carrying its original opaque credential.
        replay = await http.post(
            PATH, json=submitted, headers={"Cookie": f"{SESSION_COOKIE}={CREDENTIAL.value}"}
        )
        assert replay.status_code == HTTPStatus.OK
        assert replay.json() == body
        assert len(replay.headers.get_list("Set-Cookie")) == 1
        assert http.cookies.get(UNRELATED_OUTCOME_COOKIE) == UNRELATED_OUTCOME_VALUE
        store.calls = []
        # The unrelated future proof cookie +workflow UUID grants no deletion/status authority.
        no_session = await http.post(PATH, json=submitted)
        assert no_session.status_code == HTTPStatus.UNAUTHORIZED
        assert not store.calls
    assert len(store.deletion_sources) == 1
    assert len(store.canonical) == 1
    assert len(store.intents) == 1
    for result in (response, replay):
        assert result.headers["Cache-Control"] == "no-store"
        assert result.headers["Referrer-Policy"] == "no-referrer"
        for forbidden in (
            "erased",
            "restore",
            "purge",
            "credential",
            "csrf",
            "token",
            "reason",
            "account_id",
            "session_id",
        ):
            assert forbidden not in result.text


async def test_banned_unverified_unactivated_account_management_permitted() -> None:
    store = DeletionStore()
    account = store.actor.session.account_id
    store.actor = replace(
        store.actor, banned=True, membership=None, registration=None, activation_complete=False
    )
    store.targets[account] = AccountLifecycle(account, banned_at=NOW)
    async with client(store) as http:
        response = await http.post(PATH, json={"workflow_id": str(WORKFLOW)})
    assert response.status_code == HTTPStatus.OK
    assert store.targets[account].banned_at == NOW
    assert store.targets[account].deleted_at == NOW


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"workflow_id": "private-invalid-workflow"},
        {"workflow_id": None},
        {"workflow_id": True},
        {"workflow_id": []},
    ],
)
async def test_closed_uuid_body_sanitized_before_any_private_lookup(
    body: dict[str, object],
) -> None:
    store = DeletionStore()
    async with client(store) as http:
        response = await http.post(PATH, json=body)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["code"] == "invalid_fields"
    assert "private-invalid-workflow" not in response.text
    assert "Set-Cookie" not in response.headers
    assert not store.calls
    assert store.received_deletion_scope is None


@pytest.mark.parametrize(
    "field",
    [
        "actor_id",
        "account_id",
        "session_id",
        "deleted_at",
        "source_version",
        "restore",
        "purge",
        "proof_token",
        "mfa",
        "recent_auth",
    ],
)
async def test_extra_authority_or_fake_erasure_and_auth_fields_rejected(field: str) -> None:
    store = DeletionStore()
    async with client(store) as http:
        response = await http.post(
            PATH, json={"workflow_id": str(WORKFLOW), field: "private-extra"}
        )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-extra" not in response.text
    assert not store.calls
    assert not store.intents


@pytest.mark.parametrize(
    "fault", ["cookie", "origin", "foreign_origin", "csrf", "bad_csrf", "key", "bad_key"]
)
async def test_actual_write_credential_security_hooks_before_usecase(fault: str) -> None:
    store = DeletionStore()
    expected = HTTPStatus.FORBIDDEN
    async with client(store) as http:
        if fault == "cookie":
            http.cookies.delete(SESSION_COOKIE, domain=HOST, path="/")
            expected = HTTPStatus.UNAUTHORIZED
        elif fault == "origin":
            del http.headers["Origin"]
        elif fault == "foreign_origin":
            http.headers["Origin"] = "https://foreign.test"
        elif fault == "csrf":
            del http.headers["X-CSRF-Token"]
        elif fault == "bad_csrf":
            http.headers["X-CSRF-Token"] = "bad"
        elif fault == "key":
            del http.headers["Idempotency-Key"]
            expected = HTTPStatus.UNPROCESSABLE_ENTITY
        else:
            http.headers["Idempotency-Key"] = "bad"
            expected = HTTPStatus.UNPROCESSABLE_ENTITY
        response = await http.post(PATH, json={"workflow_id": str(WORKFLOW)})
    assert response.status_code == expected
    assert "Set-Cookie" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert not store.calls
    assert not store.intents


@pytest.mark.parametrize("fault", ["workflow", "proof", "expired_workflow", "target"])
async def test_missing_owned_workflow_or_account_neutral404_never_clears_cookies(
    fault: str,
) -> None:
    store = DeletionStore()
    workflow = WORKFLOW
    if fault == "workflow":
        workflow = uuid4()
    elif fault == "proof":
        store.proof_available = False
    elif fault == "expired_workflow":
        store.authorization = replace(store.authorization, expires_at=NOW)
    else:
        del store.targets[store.actor.session.account_id]
    async with client(store) as http:
        response = await http.post(PATH, json={"workflow_id": str(workflow)})
        assert http.cookies.get(SESSION_COOKIE) == CREDENTIAL.value
        assert http.cookies.get(UNRELATED_OUTCOME_COOKIE) == UNRELATED_OUTCOME_VALUE
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["code"] == (
        "lifecycle_target_unavailable" if fault == "target" else "deletion_workflow_unavailable"
    )
    assert "Set-Cookie" not in response.headers
    assert "deleted_at" not in response.text
    assert not store.intents
    assert not store.deletion_sources


async def test_original_revoked_credential_new_intent_denied_and_altered_workflow_conflicts() -> (
    None
):
    store = DeletionStore()
    async with client(store) as http:
        key = http.headers["Idempotency-Key"]
        first = await http.post(PATH, json={"workflow_id": str(WORKFLOW)})
        assert first.status_code == HTTPStatus.OK
        original_cookie = {"Cookie": f"{SESSION_COOKIE}={CREDENTIAL.value}"}
        http.headers["Idempotency-Key"] = "new-key-after-deletion"
        denied = await http.post(PATH, json={"workflow_id": str(WORKFLOW)}, headers=original_cookie)
        assert denied.status_code == HTTPStatus.UNAUTHORIZED
        assert "Set-Cookie" not in denied.headers
        store.authorization = replace(store.authorization, id=uuid4())
        http.headers["Idempotency-Key"] = key
        conflict = await http.post(
            PATH, json={"workflow_id": str(store.authorization.id)}, headers=original_cookie
        )
    assert conflict.status_code == HTTPStatus.CONFLICT
    assert conflict.json()["code"] == "idempotency_conflict"
    assert "Set-Cookie" not in conflict.headers
    assert len(store.deletion_sources) == 1
    assert len(store.intents) == 1


@pytest.mark.parametrize("phase", ["apply", "remember", "commit", "session", "workflow"])
async def test_failed_or_expired_submission_no_success_receipt_or_cookie_clear(phase: str) -> None:
    store = DeletionStore()
    store.fail_apply = phase == "apply"
    store.fail_remember = phase == "remember"
    store.fail_commit = phase == "commit"
    store.expire_after_apply = phase == "session"
    store.expire_workflow_after_apply = phase == "workflow"
    expected = (
        HTTPStatus.UNAUTHORIZED
        if phase == "session"
        else HTTPStatus.NOT_FOUND
        if phase == "workflow"
        else HTTPStatus.SERVICE_UNAVAILABLE
    )
    async with client(store) as http:
        response = await http.post(PATH, json={"workflow_id": str(WORKFLOW)})
        assert http.cookies.get(SESSION_COOKIE) == CREDENTIAL.value
        assert http.cookies.get(UNRELATED_OUTCOME_COOKIE) == UNRELATED_OUTCOME_VALUE
    assert response.status_code == expected
    if expected == HTTPStatus.SERVICE_UNAVAILABLE:
        assert response.headers["Retry-After"] == "1"
    assert "Set-Cookie" not in response.headers
    assert "deleted_at" not in response.text
    assert not store.deletion_sources
    assert not store.intents
    assert store.actor.deleted_at is None
    assert store.actor.session.revoked_at is None


async def test_actual_observer_no_credential_csrf_proof_or_intent_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = DeletionStore()
    caplog.set_level("INFO", logger="studymate.http")
    async with client(store) as http:
        key = http.headers["Idempotency-Key"]
        csrf = http.headers["X-CSRF-Token"]
        response = await http.post(PATH, json={"workflow_id": str(WORKFLOW)})
    assert response.status_code == HTTPStatus.OK
    records = [record for record in caplog.records if record.name == "studymate.http"]
    assert len(records) == 1
    data = repr([record.__dict__ for record in records])
    for secret in (CREDENTIAL.value, key, csrf, UNRELATED_OUTCOME_VALUE, "synthetic-login-cookie"):
        assert secret not in data


def test_single_factory_schema_closed_problem_types_no_recovery_route_or_cookie_spec() -> None:
    schema = application(DeletionStore()).openapi()
    assert tuple(schema["paths"]) == (PATH,)
    operation = schema["paths"][PATH]["post"]
    for status in ("401", "403", "404", "409", "422", "503"):
        assert operation["responses"][status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ProblemResponse"
        }
    assert operation["security"] == [{"SessionCookie": []}]
    components = schema["components"]["schemas"]
    assert "HTTPValidationError" not in components
    assert "ValidationError" not in components
    assert components["DeleteAccountBody"]["additionalProperties"] is False
    assert set(components["DeleteAccountBody"]["properties"]) == {"workflow_id"}
    assert components["DeletionReceiptResponse"]["additionalProperties"] is False
    assert set(components["DeletionReceiptResponse"]["properties"]) == {
        "workflow_id",
        "deleted_at",
        "source_version",
    }
    error = RuntimeError("Unclassified internal private failure")
    with pytest.raises(RuntimeError, match="Unclassified"):
        deletion_problem(error)
