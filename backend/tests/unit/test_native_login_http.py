import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from http import HTTPStatus

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from studymate.application.identity.google import (
    GoogleAuthorization,
    GoogleCode,
    GoogleRejectedError,
)
from studymate.application.identity.login import (
    BeginGoogleLogin,
    GoogleCallbackCommand,
    LoginCompleted,
)
from studymate.application.identity.native_login import (
    BeginNativeLogin,
    BindNativeCallback,
    CancelNativeAttempt,
    CompleteLoginForClient,
    ExchangeNativeAttempt,
    IdentifyNativeCallback,
    NativeCallbackFinished,
    RegisterNativeAttempt,
)
from studymate.application.identity.sessions import SessionCredential
from studymate.domain.membership import GoogleIdentity
from studymate.infrastructure.persistence.google_login import SqlLoginUnitOfWork
from studymate.infrastructure.security.login_vault import AeadLoginVault
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.browser import SESSION_COOKIE, BrowserConfiguration
from studymate.presentation.identity import LOGIN_COOKIE
from studymate.presentation.native_login import NativeServices, native_router
from tests.unit.test_native_login import BROWSER, PROVISIONAL, VERIFIER, MemoryNative, prepared

ORIGIN = "https://peerly.example.test"


class ForbiddenProvider:
    async def authorization_url(self, authorization: GoogleAuthorization) -> str:
        del authorization
        raise AssertionError("No provider operation is allowed in this test")

    async def exchange(
        self, code: GoogleCode, authorization: GoogleAuthorization
    ) -> GoogleIdentity:
        del code, authorization
        raise AssertionError("No provider operation is allowed in this test")


class Signer:
    async def csrf_token(self, credential: SessionCredential) -> str:
        del credential
        raise AssertionError("No CSRF generation is allowed in this test")

    async def valid_csrf(self, credential: SessionCredential, token: str) -> bool:
        del credential, token
        raise AssertionError("Native exchange uses its proof, not a fabricated CSRF token")

    async def source_digest(self, address: str) -> bytes:
        return hashlib.sha256(address.encode()).digest()


def services(memory: MemoryNative) -> NativeServices:
    vault = AeadLoginVault(bytes(range(32)))
    hasher = Sha256SessionHasher()
    # No engine/URL: invalid challenge must reject before any DB/provider work.
    begin = BeginGoogleLogin(SqlLoginUnitOfWork(async_sessionmaker()), ForbiddenProvider(), vault)
    return NativeServices(
        Signer(),
        BeginNativeLogin(begin, RegisterNativeAttempt(memory, hasher)),
        ExchangeNativeAttempt(memory, hasher, vault),
        BrowserConfiguration(ORIGIN, frozenset({ORIGIN})),
        "dev.alekseiorlov.peerly://auth/complete",
    )


@asynccontextmanager
async def client(native: NativeServices) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(native_router(native))
    async with AsyncClient(transport=ASGITransport(app), base_url=ORIGIN) as opened:
        yield opened


async def test_exchange_uses_only_secure_http_only_cookie_not_body_or_redirect() -> None:
    memory, attempt_id = await prepared()
    native = services(memory)
    await BindNativeCallback(memory, Sha256SessionHasher())(BROWSER, PROVISIONAL)
    async with client(native) as http:
        response = await http.post(
            "/api/v1/auth/native/exchange",
            headers={"Origin": ORIGIN},
            json={
                "attempt_id": str(attempt_id),
                "verifier": VERIFIER,
            },
        )
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.content == b""
    assert "location" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(SESSION_COOKIE + "=")
    assert all(flag in cookie for flag in ("HttpOnly", "Secure", "Path=/", "SameSite=lax"))
    assert "Domain=" not in cookie


async def test_pending_and_foreign_origin_do_not_create_or_deliver_sessions() -> None:
    memory, attempt_id = await prepared()
    native = services(memory)
    async with client(native) as http:
        payload = {"attempt_id": str(attempt_id), "verifier": VERIFIER}
        denied = await http.post("/api/v1/auth/native/exchange", json=payload)
        assert denied.status_code == HTTPStatus.FORBIDDEN
        pending = await http.post(
            "/api/v1/auth/native/exchange", headers={"Origin": ORIGIN}, json=payload
        )
        assert pending.status_code == HTTPStatus.CONFLICT
        invalid = await http.post(
            "/api/v1/auth/native/exchange",
            headers={"Origin": ORIGIN},
            json={
                **payload,
                "verifier": "D" * 43,
            },
        )
        assert invalid.status_code == HTTPStatus.BAD_REQUEST
        assert all("set-cookie" not in response.headers for response in (denied, pending, invalid))


async def test_native_completion_has_only_fixed_user_gesture_link_and_no_web_session_cookie() -> (
    None
):
    memory, _ = await prepared()
    native = services(memory)
    completed = await complete_client(memory)(callback_command(BROWSER))
    assert isinstance(completed, NativeCallbackFinished)
    assert completed.succeeded
    redirect = native.finish()
    assert redirect.status_code == HTTPStatus.SEE_OTHER
    assert redirect.headers["location"] == ORIGIN + "/api/v1/auth/native/return"
    assert SESSION_COOKIE not in redirect.headers.get("set-cookie", "")
    assert LOGIN_COOKIE in redirect.headers["set-cookie"]
    async with client(native) as http:
        response = await http.get("/api/v1/auth/native/return")
    assert response.status_code == HTTPStatus.OK
    assert "dev.alekseiorlov.peerly://auth/complete" in response.text
    assert "?" not in response.text
    assert "set-cookie" not in response.headers
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    for secret in (VERIFIER, BROWSER.value, PROVISIONAL.value):
        assert secret not in response.text


async def test_native_failure_is_terminal_and_wakes_without_provider_error_or_identity() -> None:
    memory, attempt_id = await prepared()
    native = services(memory)
    completed = await complete_client(memory, reject=True)(callback_command(BROWSER))
    assert isinstance(completed, NativeCallbackFinished)
    assert not completed.succeeded
    response = native.finish()
    assert response.status_code == HTTPStatus.SEE_OTHER
    assert memory.attempts[attempt_id].cancelled_at is not None
    async with client(native) as http:
        rejected = await http.post(
            "/api/v1/auth/native/exchange",
            headers={"Origin": ORIGIN},
            json={
                "attempt_id": str(attempt_id),
                "verifier": VERIFIER,
            },
        )
        assert rejected.status_code == HTTPStatus.BAD_REQUEST


async def test_invalid_challenge_rejects_before_provider_or_database_access() -> None:
    memory, attempt_id = await prepared()
    async with client(services(memory)) as http:
        rejected = await http.get(
            "/api/v1/auth/native/start",
            params={
                "attempt_id": str(attempt_id),
                "challenge": "not-a-challenge",
            },
        )
        assert rejected.status_code == HTTPStatus.BAD_REQUEST
        assert "set-cookie" not in rejected.headers


@dataclass
class MemoryCompletion:
    reject: bool = False
    received: list[GoogleCallbackCommand] = field(default_factory=list)

    async def __call__(self, command: GoogleCallbackCommand) -> LoginCompleted:
        self.received.append(command)
        if self.reject:
            raise GoogleRejectedError
        return LoginCompleted(PROVISIONAL, "/onboarding")


def complete_client(memory: MemoryNative, reject: bool = False) -> CompleteLoginForClient:
    hasher = Sha256SessionHasher()
    return CompleteLoginForClient(
        IdentifyNativeCallback(memory, hasher),
        MemoryCompletion(reject),
        BindNativeCallback(memory, hasher),
        CancelNativeAttempt(memory, hasher),
    )


def callback_command(browser: SessionCredential) -> GoogleCallbackCommand:
    return GoogleCallbackCommand(
        bytes(32),
        "synthetic-state",
        browser,
        "synthetic-code",
        previous=SessionCredential("D" * 43),
    )


async def test_web_callback_keeps_previous_session_while_native_omits_it() -> None:
    memory, _ = await prepared()
    hasher = Sha256SessionHasher()
    google = MemoryCompletion()
    complete = CompleteLoginForClient(
        IdentifyNativeCallback(memory, hasher),
        google,
        BindNativeCallback(memory, hasher),
        CancelNativeAttempt(memory, hasher),
    )
    native = await complete(callback_command(BROWSER))
    assert isinstance(native, NativeCallbackFinished)
    assert google.received[-1].previous is None
    ordinary = callback_command(SessionCredential("E" * 43))
    web = await complete(ordinary)
    assert isinstance(web, LoginCompleted)
    assert google.received[-1] == ordinary
