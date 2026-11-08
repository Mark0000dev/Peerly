from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.lifecycle.recovery import PrepareOwnDeletion, ReadOwnDeletionStatus
from studymate.domain.lifecycle.states import DeletionRevision
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.lifecycle.recovery import (
    DELETION_STATUS_COOKIE,
    DeletionRecoveryHttpServices,
    deletion_recovery_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.test_deletion_recovery import HASHER, PROOFS, RecoveryStore

ORIGIN = "https://recovery.test"
SIGNER = HmacBrowserTokenSigner(b"b" * 32)


def store_now() -> RecoveryStore:
    store = RecoveryStore()
    store.clock = datetime.now(UTC)
    store.actor = replace(
        store.actor,
        session=replace(
            store.actor.session,
            issued_at=store.clock - timedelta(minutes=1),
            expires_at=store.clock + timedelta(hours=1),
        ),
    )
    return store


def application(store: RecoveryStore) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        deletion_recovery_router(
            DeletionRecoveryHttpServices(
                PrepareOwnDeletion(store, HASHER, PROOFS),
                ReadOwnDeletionStatus(store, PROOFS),
                SIGNER,
                BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
            )
        )
    )
    return app


@asynccontextmanager
async def client(store: RecoveryStore) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=application(store)),
        base_url=ORIGIN,
        cookies={SESSION_COOKIE: CREDENTIAL.value},
    ) as http:
        http.headers.update({"Origin": ORIGIN, "X-CSRF-Token": await SIGNER.csrf_token(CREDENTIAL)})
        yield http


async def test_preflight_cookie_is_stable_secret_http_only_and_status_has_separate_authority() -> (
    None
):
    store = store_now()
    async with client(store) as http:
        first = await http.post("/api/v1/me/deletion-workflows", json={})
        assert first.status_code == HTTPStatus.OK
        cookie = first.headers["set-cookie"]
        assert DELETION_STATUS_COOKIE in cookie
        assert "Secure" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert "Path=/" in cookie
        assert "Domain=" not in cookie
        proof = http.cookies[DELETION_STATUS_COOKIE]
        assert proof not in first.text
        assert CREDENTIAL.value not in first.text
        assert (await http.post("/api/v1/me/deletion-workflows", json={})).json() == first.json()
        assert http.cookies[DELETION_STATUS_COOKIE] == proof
        assert store.creations == 1
        http.cookies.delete(SESSION_COOKIE)
        pending = await http.get("/api/v1/me/deletion-status")
        assert pending.status_code == HTTPStatus.OK
        assert pending.json()["state"] == "pending"
        assert pending.json()["workflow_id"] == first.json()["workflow_id"]
        assert pending.headers["cache-control"] == "no-store"
        assert pending.headers["referrer-policy"] == "no-referrer"
        forbidden = await http.post("/api/v1/me/deletion-workflows", json={})
        assert forbidden.status_code == HTTPStatus.UNAUTHORIZED


async def test_deleted_session_is_not_recreated_by_confirmed_status_read() -> None:
    store = store_now()
    async with client(store) as http:
        prepared = await http.post("/api/v1/me/deletion-workflows", json={})
        assert prepared.status_code == HTTPStatus.OK
        assert store.workflow is not None
        authorization = store.workflow.authorization
        store.deletion = DeletionRevision(
            uuid4(),
            authorization.account_id,
            1,
            store.clock,
            authorization.session_id,
            authorization.id,
        )
        store.actor = replace(
            store.actor,
            deleted_at=store.clock,
            session=replace(store.actor.session, revoked_at=store.clock),
        )
        http.cookies.delete(SESSION_COOKIE)
        result = await http.get("/api/v1/me/deletion-status")
        assert result.status_code == HTTPStatus.OK
        assert result.json()["state"] == "deleted"
        assert result.json()["source_version"] == 1
        assert "set-cookie" not in result.headers
        assert SESSION_COOKIE not in http.cookies
        assert store.actor.deleted_at == store.clock


@pytest.mark.parametrize("proof", [None, "wrong", "z" * 43])
async def test_workflow_id_or_application_cookie_cannot_replace_the_status_proof(
    proof: str | None,
) -> None:
    store = store_now()
    async with client(store) as http:
        prepared = await http.post("/api/v1/me/deletion-workflows", json={})
        assert prepared.status_code == HTTPStatus.OK
        http.cookies.delete(DELETION_STATUS_COOKIE)
        if proof is not None:
            http.cookies.set(DELETION_STATUS_COOKIE, proof)
        result = await http.get(
            "/api/v1/me/deletion-status", params={"workflow_id": prepared.json()["workflow_id"]}
        )
        assert result.status_code == HTTPStatus.NOT_FOUND
        assert result.json()["code"] == "deletion_status_unavailable"
        assert "workflow_id" not in result.json()


@pytest.mark.parametrize("failure", ["commit", "expired", "origin", "csrf", "extra"])
async def test_failed_preflight_does_not_issue_or_replace_status_proof(failure: str) -> None:
    store = store_now()
    async with client(store) as http:
        body: dict[str, str] = {}
        if failure == "commit":
            store.fail_commit = True
        elif failure == "expired":
            store.expire_on_create = True
        elif failure == "origin":
            http.headers["Origin"] = "https://foreign.test"
        elif failure == "csrf":
            http.headers["X-CSRF-Token"] = "wrong"
        else:
            body = {"account_id": "PRIVATE client override"}
        response = await http.post("/api/v1/me/deletion-workflows", json=body)
        expected = {
            "commit": HTTPStatus.SERVICE_UNAVAILABLE,
            "expired": HTTPStatus.NOT_FOUND,
            "origin": HTTPStatus.FORBIDDEN,
            "csrf": HTTPStatus.FORBIDDEN,
            "extra": HTTPStatus.UNPROCESSABLE_ENTITY,
        }
        assert response.status_code == expected[failure]
        assert "set-cookie" not in response.headers
        assert DELETION_STATUS_COOKIE not in http.cookies
        assert "PRIVATE client override" not in response.text
        if failure == "commit":
            assert response.headers["retry-after"] == "1"


async def test_status_expiry_is_not_a_claim_of_unsent_or_reverted_deletion() -> None:
    store = store_now()
    async with client(store) as http:
        await http.post("/api/v1/me/deletion-workflows", json={})
        assert store.workflow is not None
        store.clock = store.workflow.authorization.expires_at
        response = await http.get("/api/v1/me/deletion-status")
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert response.json()["code"] == "deletion_status_unavailable"
        assert "failed" not in response.text
        assert "restored" not in response.text


def test_status_schema_requires_its_distinct_cookie_and_has_only_closed_declared_models() -> None:
    schema = application(store_now()).openapi()
    status = schema["paths"]["/api/v1/me/deletion-status"]["get"]
    assert status["security"] == [{"DeletionStatusCookie": []}]
    assert "parameters" not in status
    prepare = schema["paths"]["/api/v1/me/deletion-workflows"]["post"]
    assert prepare["security"] == [{"SessionCookie": []}]
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    assert "ValidationError" not in schema["components"]["schemas"]
    assert (
        schema["components"]["schemas"]["DeletionPreparationBody"]["additionalProperties"] is False
    )
