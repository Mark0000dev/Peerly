from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.domain.lifecycle.states import MAX_LIFECYCLE_REASON_CHARACTERS, AccountLifecycle
from studymate.infrastructure.observability.http import JsonHttpObserver
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.lifecycle.ban_router import BanHttpServices, ban_problem, ban_router
from studymate.presentation.request_correlation import RequestCorrelation
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.lifecycle.ban_store import BanStore
from tests.unit.lifecycle.test_bans import change
from tests.unit.lifecycle.test_states import ACCOUNT, REASON

ORIGIN = "https://lifecycle.test"
SIGNER = HmacBrowserTokenSigner(b"b" * 32)
PATH = f"/api/v1/operator/accounts/{ACCOUNT}/ban"


def application(store: BanStore) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        ban_router(
            BanHttpServices(
                change(store), SIGNER, BrowserConfiguration(ORIGIN, frozenset({ORIGIN}))
            )
        )
    )
    return app


@asynccontextmanager
async def client(store: BanStore) -> AsyncIterator[AsyncClient]:
    app = application(store)
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


async def test_real_usecase_ban_unban_and_old_receipt_replay_do_not_echo_private_input() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    store.targets[ACCOUNT] = AccountLifecycle(ACCOUNT, deleted_at=NOW)
    async with client(store) as http:
        original = await http.put(PATH, json={"banned": True, "reason": REASON})
        unban = await http.put(PATH, json={"banned": False, "reason": "  Actual unban reason  "})
        replay = await http.put(PATH, json={"banned": True, "reason": REASON})
    assert original.status_code == HTTPStatus.OK
    assert unban.status_code == HTTPStatus.OK
    assert replay.status_code == HTTPStatus.OK
    assert original.json() == replay.json()
    assert original.json()["changed"] is True
    assert original.json()["account"]["source_version"] == 1
    assert original.json()["revision"]["id"] == str(store.sources[0].id)
    assert original.json()["representation"] == "committed_command_receipt_not_current_account_read"
    assert unban.json()["revision"]["banned"] is False
    assert unban.json()["account"]["deleted_at"] is not None
    assert unban.json()["account"]["banned_at"] is None
    assert store.targets[ACCOUNT].banned_at is None
    assert store.targets[ACCOUNT].deleted_at == NOW
    assert store.sources[0].reason.value == REASON
    assert len(store.sources) == len((original, unban))
    for response in (original, unban, replay):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        for private in (
            "reason",
            "credential",
            "intent_key",
            "fingerprint",
            "actor_session",
            "operator_access",
        ):
            assert private not in response.text
        assert REASON.strip() not in response.text
    assert not store.audit


async def test_noop_legacy_receipt_has_no_invented_source_and_unicode_limit_is_characters() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    store.targets[ACCOUNT] = AccountLifecycle(ACCOUNT, banned_at=NOW)
    async with client(store) as http:
        response = await http.put(
            PATH, json={"banned": True, "reason": "あ" * MAX_LIFECYCLE_REASON_CHARACTERS}
        )
    assert response.status_code == HTTPStatus.OK
    assert response.json()["changed"] is False
    assert response.json()["revision"] is None
    assert response.json()["account"]["source_version"] == 0
    assert not store.sources
    assert not store.canonical
    assert len(store.intents) == 1


@pytest.mark.parametrize("value", [1, 0, "true", "false", None, [], {}])
async def test_banned_requires_actual_json_boolean(value: object) -> None:
    store = BanStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.put(PATH, json={"banned": value, "reason": REASON})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["code"] == "invalid_fields"
    assert REASON.strip() not in response.text
    assert not store.calls
    assert store.received_scope is None


@pytest.mark.parametrize(
    "reason", ["", " \n ", "private-overlength-" * (MAX_LIFECYCLE_REASON_CHARACTERS // 2)]
)
async def test_invalid_reason_sanitized_before_business_usecase(reason: str) -> None:
    store = BanStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.put(PATH, json={"banned": True, "reason": reason})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-overlength" not in response.text
    assert not store.calls
    assert store.received_scope is None


@pytest.mark.parametrize(
    "field",
    [
        "actor_id",
        "operator_access_version",
        "deleted_at",
        "source_version",
        "session_id",
        "workflow_id",
        "restore",
        "purge",
    ],
)
async def test_closed_body_rejects_arbitrary_authority_or_lifecycle_state(field: str) -> None:
    store = BanStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.put(
            PATH, json={"banned": True, "reason": REASON, field: "private-extra"}
        )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-extra" not in response.text
    assert not store.calls


@pytest.mark.parametrize(
    "fault",
    [
        "missing_cookie",
        "bad_cookie",
        "missing_origin",
        "foreign_origin",
        "missing_csrf",
        "bad_csrf",
        "missing_key",
        "invalid_key",
        "no_role",
    ],
)
async def test_real_cookie_origin_csrf_idempotent_header_and_db_role_hooks(fault: str) -> None:
    store = BanStore()
    store.assign_explicit_operator()
    expected = HTTPStatus.FORBIDDEN
    async with client(store) as http:
        if fault == "missing_cookie":
            http.cookies.clear()
            expected = HTTPStatus.UNAUTHORIZED
        elif fault == "bad_cookie":
            http.cookies.clear()
            http.cookies.set(SESSION_COOKIE, "invalid")
            expected = HTTPStatus.UNAUTHORIZED
        elif fault == "missing_origin":
            del http.headers["Origin"]
        elif fault == "foreign_origin":
            http.headers["Origin"] = "https://foreign.test"
        elif fault == "missing_csrf":
            del http.headers["X-CSRF-Token"]
        elif fault == "bad_csrf":
            http.headers["X-CSRF-Token"] = "invalid"
        elif fault == "missing_key":
            del http.headers["Idempotency-Key"]
            expected = HTTPStatus.UNPROCESSABLE_ENTITY
        elif fault == "invalid_key":
            http.headers["Idempotency-Key"] = "bad"
            expected = HTTPStatus.UNPROCESSABLE_ENTITY
        else:
            store.access = None
            http.headers["X-Operator"] = "true"
        response = await http.put(PATH, json={"banned": True, "reason": REASON})
    assert response.status_code == expected
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert not store.calls
    assert not store.intents
    assert not store.sources


async def test_invalid_uuid_missing_target_and_changed_intent_problem_mappings() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        invalid = await http.put(
            PATH.replace(str(ACCOUNT), "private-invalid-account"),
            json={"banned": True, "reason": REASON},
        )
        assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "private-invalid-account" not in invalid.text
        missing = await http.put(
            PATH.replace(str(ACCOUNT), str(uuid4())), json={"banned": True, "reason": REASON}
        )
        assert missing.status_code == HTTPStatus.NOT_FOUND
        assert missing.json()["code"] == "lifecycle_target_unavailable"
        first = await http.put(PATH, json={"banned": True, "reason": REASON})
        assert first.status_code == HTTPStatus.OK
        conflict = await http.put(PATH, json={"banned": True, "reason": REASON + " "})
    assert conflict.status_code == HTTPStatus.CONFLICT
    assert conflict.json()["code"] == "idempotency_conflict"
    assert "reason" not in conflict.text
    assert len(store.sources) == 1


@pytest.mark.parametrize("phase", ["apply", "remember", "commit", "expiry"])
async def test_atomic_failure_safe503_retry_or401_never_echoes_reason(phase: str) -> None:
    store = BanStore()
    store.assign_explicit_operator()
    store.fail_apply = phase == "apply"
    store.fail_remember = phase == "remember"
    store.fail_commit = phase == "commit"
    store.expire_after_apply = phase == "expiry"
    async with client(store) as http:
        response = await http.put(PATH, json={"banned": True, "reason": REASON})
    assert response.status_code == (
        HTTPStatus.UNAUTHORIZED if phase == "expiry" else HTTPStatus.SERVICE_UNAVAILABLE
    )
    if phase != "expiry":
        assert response.headers["Retry-After"] == "1"
    assert REASON.strip() not in response.text
    assert "reason" not in response.text
    assert store.targets[ACCOUNT].banned_at is None
    assert not store.intents
    assert not store.sources
    assert not store.canonical


def test_factory_schema_closed_problem_types_and_no_unknown_error_success() -> None:
    store = BanStore()
    schema = application(store).openapi()
    assert tuple(schema["paths"]) == ("/api/v1/operator/accounts/{account_id}/ban",)
    operation = schema["paths"]["/api/v1/operator/accounts/{account_id}/ban"]["put"]
    for status in ("401", "403", "404", "409", "422", "503"):
        assert operation["responses"][status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ProblemResponse"
        }
    assert operation["security"] == [{"SessionCookie": []}]
    components = schema["components"]["schemas"]
    assert "HTTPValidationError" not in components
    assert "ValidationError" not in components
    assert components["ChangeBanBody"]["additionalProperties"] is False
    assert components["ChangeBanBody"]["properties"]["banned"]["type"] == "boolean"
    for name in ("BanChangeResponse", "BanReceiptSource", "BanReceiptState"):
        assert components[name]["additionalProperties"] is False
        for private in ("reason", "credential", "fingerprint", "intent_key"):
            assert private not in components[name]["properties"]
    error = RuntimeError("Unclassified private internal failure")
    with pytest.raises(RuntimeError, match="Unclassified"):
        ban_problem(error)


async def test_unknown_actual_session_and_banned_actor_do_not_gain_operator_authority() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        store.missing_identity = True
        absent = await http.put(PATH, json={"banned": True, "reason": REASON})
        assert absent.status_code == HTTPStatus.UNAUTHORIZED
        store.missing_identity = False
        store.actor = replace(store.actor, banned=True)
        banned = await http.put(PATH, json={"banned": False, "reason": REASON})
        assert banned.status_code == HTTPStatus.FORBIDDEN
    assert not store.calls
    assert not store.intents


async def test_actual_http_observer_has_no_private_reason_credentials_or_intent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = BanStore()
    store.assign_explicit_operator()
    app = application(store)
    app.add_middleware(RequestCorrelation, observer=JsonHttpObserver())
    key = str(uuid4())
    csrf = await SIGNER.csrf_token(CREDENTIAL)
    caplog.set_level("INFO", logger="studymate.http")
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url=ORIGIN,
            cookies={SESSION_COOKIE: CREDENTIAL.value},
        ) as http,
    ):
        http.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": key})
        good = await http.put(PATH, json={"banned": True, "reason": REASON})
        conflict = await http.put(PATH, json={"banned": True, "reason": REASON + " "})
    assert good.status_code == HTTPStatus.OK
    assert conflict.status_code == HTTPStatus.CONFLICT
    records = [record for record in caplog.records if record.name == "studymate.http"]
    assert len(records) == len((good, conflict))
    encoded = repr([record.__dict__ for record in records])
    for private in ("Private original lifecycle reason", CREDENTIAL.value, csrf, key):
        assert private not in encoded
    assert store.sources[0].reason.value == REASON
    assert not store.audit


async def test_control_character_reason_rejected_before_hmac_or_persistence() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        response = await http.put(PATH, json={"banned": True, "reason": "private\x00reason"})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["code"] == "invalid_fields"
    assert "private" not in response.text
    assert store.received_scope is None
    assert not store.intents
    assert not store.sources
