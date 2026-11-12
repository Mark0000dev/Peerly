"""Actual role/usecase behind same-origin CSRF, without placeholder or OTP inputs."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from studymate.application.operator.membership_verification import ReadManualMembershipContext
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.operator.membership_verification_router import (
    ManualMembershipHttpServices,
    operator_membership_verification_router,
)
from studymate.presentation.request_errors import validation_problem
from tests.unit.identity_store import CREDENTIAL
from tests.unit.operator.membership_verification_store import (
    CHALLENGE_ID,
    EMAIL,
    GOOGLE_ID,
    ManualVerificationStore,
)
from tests.unit.operator.membership_verification_usecases_test import verify
from tests.unit.operator.store import TARGET

ORIGIN = "https://operator.test"
SIGNER = HmacBrowserTokenSigner(b"b" * 32)
ROOT = f"/api/v1/operator/accounts/{TARGET}"


def body() -> dict[str, str]:
    return {
        "expected_google_identity_id": str(GOOGLE_ID),
        "expected_challenge_id": str(CHALLENGE_ID),
        "expected_email": EMAIL.value,
    }


@asynccontextmanager
async def client(store: ManualVerificationStore) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_problem)
    app.include_router(
        operator_membership_verification_router(
            ManualMembershipHttpServices(
                ReadManualMembershipContext(store, Sha256SessionHasher()),
                verify(store),
                SIGNER,
                BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
            )
        )
    )
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


async def test_manual_receipt_and_owned_context_never_claim_otp_or_activation() -> None:
    store = ManualVerificationStore()
    store.assign_explicit_operator()
    async with client(store) as http:
        before = await http.get(ROOT + "/membership-verification")
        result = await http.post(ROOT + "/membership-verifications", json=body())
        replay = await http.post(ROOT + "/membership-verifications", json=body())
        after = await http.get(ROOT + "/membership-verification")
    assert before.status_code == result.status_code == after.status_code == HTTPStatus.OK
    assert result.json() == replay.json()
    assert result.json()["proof"] == "manual_operator_attestation"
    assert result.json()["otp_consumed"] is False
    assert result.json()["activation_granted"] is False
    assert after.json()["manual_verification"]["id"] == result.json()["id"]
    assert result.headers["Cache-Control"] == "no-store"
    assert EMAIL.value not in result.text
    assert len(store.sources) == 1


@pytest.mark.parametrize("guard", ["origin", "csrf", "cookie", "role"])
async def test_no_public_auth_or_cookie_alone_grants_manual_membership(guard: str) -> None:
    store = ManualVerificationStore()
    if guard != "role":
        store.assign_explicit_operator()
    async with client(store) as http:
        if guard == "origin":
            http.headers["Origin"] = "https://other.invalid"
        elif guard == "csrf":
            http.headers.pop("X-CSRF-Token")
        elif guard == "cookie":
            http.cookies.clear()
        result = await http.post(ROOT + "/membership-verifications", json=body())
    assert result.status_code == (
        HTTPStatus.UNAUTHORIZED if guard == "cookie" else HTTPStatus.FORBIDDEN
    )
    assert not store.sources


@pytest.mark.parametrize(
    "forbidden", ["mode", "placeholder", "code", "performed_by", "operator_access_version"]
)
async def test_extra_client_authority_and_synthetic_or_otp_modes_have_no_wire_slot(
    forbidden: str,
) -> None:
    store = ManualVerificationStore()
    store.assign_explicit_operator()
    supplied = body()
    supplied[forbidden] = "private-sentinel"
    async with client(store) as http:
        result = await http.post(ROOT + "/membership-verifications", json=supplied)
    assert result.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "private-sentinel" not in result.text
    assert not store.sources
