"""HTTP adapter only: real signer, router and header DTO; no app lifespan or DB."""

from dataclasses import replace
from http import HTTPStatus
from uuid import uuid4

import httpx2
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.identity.sessions import Logout
from studymate.application.student_notifications.subscriptions import LogoutInstallation
from studymate.bootstrap import _authentication_services
from studymate.config import AuthenticationConfiguration
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.identity import identity_router
from tests.unit.student_notifications.test_installation_logout import CREDENTIAL, Hasher, Store

ORIGIN = "https://schema.invalid"


def closed_provider(_request: httpx2.Request) -> httpx2.Response:
    raise AssertionError("Logout must never call a provider")


@pytest.mark.parametrize(
    "case",
    ["legacy", "matched", "foreign", "missing_cookie", "no_adapter", "csrf", "origin", "malformed"],
)
async def test_public_logout_contract_keeps_204_and_exposes_only_confirmed_retirement(
    case: str,
) -> None:
    store = Store()
    configuration = AuthenticationConfiguration(
        client_id="schema-only",
        client_secret=SecretStr("synthetic"),
        public_origin=ORIGIN,
        envelope_key=SecretStr("01" * 32),
        browser_signing_key=SecretStr("02" * 32),
        code_key=SecretStr("03" * 32),
    )
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(closed_provider)) as provider:
        services = _authentication_services(
            configuration, async_sessionmaker[AsyncSession](), provider
        )
        services = replace(
            services,
            logout=Logout(store, Hasher()),
            logout_installation=(
                None if case == "no_adapter" else LogoutInstallation(store, Hasher())
            ),
        )
        app = FastAPI()
        app.include_router(identity_router(services))
        headers = {"Origin": ORIGIN, "X-CSRF-Token": await services.signer.csrf_token(CREDENTIAL)}
        if case != "legacy":
            headers["X-Notification-Installation"] = str(
                uuid4() if case == "foreign" else store.installation
            )
        if case == "csrf":
            headers["X-CSRF-Token"] = "invalid"
        if case == "origin":
            headers["Origin"] = "https://foreign.invalid"
        if case == "malformed":
            headers["X-Notification-Installation"] = "not-a-uuid"
        async with AsyncClient(transport=ASGITransport(app), base_url=ORIGIN) as client:
            if case != "missing_cookie":
                client.cookies.set(SESSION_COOKIE, CREDENTIAL.value)
            response = await client.post("/api/v1/auth/logout", headers=headers)
        if case in ("csrf", "origin", "malformed"):
            assert response.status_code == (
                HTTPStatus.UNPROCESSABLE_ENTITY if case == "malformed" else HTTPStatus.FORBIDDEN
            )
            assert not store.revoked
            assert store.enabled
            assert "x-notification-retirement" not in response.headers
        else:
            assert response.status_code == HTTPStatus.NO_CONTENT
            assert not response.content
            assert response.headers["cache-control"] == "no-store"
            if case == "legacy":
                assert "x-notification-retirement" not in response.headers
            else:
                assert response.headers["x-notification-retirement"] == (
                    "retired" if case == "matched" else "unconfirmed"
                )
            assert store.retired == (case == "matched")
            assert store.revoked == (case != "missing_cookie")
