import json
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.email_delivery import (
    DeliverVerificationEmail,
    DeliveryStep,
    PermanentEmailError,
    VerificationEmail,
)
from studymate.application.identity.login import MAX_CALLBACK_FAILURES_PER_HOUR
from studymate.domain.membership import MAX_CODE_ATTEMPTS
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.infrastructure.persistence.email_delivery import SqlEmailWorkerUnitOfWork
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.security.email_vault import AeadEmailVault
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.command_body_limit import COMMAND_BODY_BYTES
from studymate.presentation.identity import (
    LOGIN_COOKIE,
    ChallengeResponse,
    ChallengeStatusResponse,
    IdentityResponse,
    VerificationResponse,
)
from tests.integration.http_identity import BrowserHarness, login, write_headers

pytestmark = pytest.mark.integration
ORIGIN = "https://app.test"


async def test_google_login_restricted_bootstrap_csrf_logout(browser: BrowserHarness) -> None:
    client = browser.client
    assert (await client.get("/api/v1/me")).status_code == HTTPStatus.UNAUTHORIZED
    started = await client.get("/api/v1/auth/google/start")
    assert started.status_code == HTTPStatus.SEE_OTHER
    assert started.headers["cache-control"] == "no-store"
    cookie = started.headers["set-cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Domain=" not in cookie
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    callback = await client.get(
        "/api/v1/auth/google/callback", params={"state": state, "code": "code"}
    )
    assert callback.status_code == HTTPStatus.SEE_OTHER
    assert callback.headers["location"] == ORIGIN + "/onboarding"
    assert LOGIN_COOKIE not in client.cookies
    session_secret = client.cookies[SESSION_COOKIE]
    me = await client.get("/api/v1/me")
    assert me.status_code == HTTPStatus.OK
    assert me.headers["cache-control"] == "no-store"
    result = IdentityResponse.model_validate(me.json())
    assert result.membership_status == "unverified"
    assert result.verified_at is None
    assert result.capabilities.can_verify_student_email
    assert not result.capabilities.can_use_student_features
    assert session_secret not in me.text
    assert result.csrf_token != session_secret
    rejected = await client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
    assert rejected.status_code == HTTPStatus.FORBIDDEN
    assert rejected.json()["code"] == "csrf_denied"
    assert (await client.get("/api/v1/me")).status_code == HTTPStatus.OK
    logout = await client.post(
        "/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": result.csrf_token}
    )
    assert logout.status_code == HTTPStatus.NO_CONTENT
    assert SESSION_COOKIE not in client.cookies
    assert (await client.get("/api/v1/me")).status_code == HTTPStatus.UNAUTHORIZED
    assert (
        await client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
    ).status_code == HTTPStatus.NO_CONTENT
    client.cookies.set(SESSION_COOKIE, session_secret)
    assert (await client.get("/api/v1/me")).status_code == HTTPStatus.UNAUTHORIZED
    assert (
        await client.post(
            "/api/v1/auth/logout",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": result.csrf_token,
            },
        )
    ).status_code == HTTPStatus.NO_CONTENT


@pytest.mark.parametrize("origin", [None, "https://evil.example", "null"])
async def test_logout_requires_trusted_origin(browser: BrowserHarness, origin: str | None) -> None:
    await login(browser.client)
    headers = {"Origin": origin} if origin is not None else {}
    response = await browser.client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()["code"] == "origin_denied"


async def test_bad_cookie_never_becomes_an_identity(browser: BrowserHarness) -> None:
    browser.client.cookies.set(SESSION_COOKIE, "bad-cookie")
    assert (await browser.client.get("/api/v1/me")).status_code == HTTPStatus.UNAUTHORIZED
    assert (
        await browser.client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
    ).status_code == HTTPStatus.NO_CONTENT


@pytest.mark.parametrize(
    "query",
    [
        "state=missing&code=code",
        "state=" + "x" * 43 + "&code=code",
        "state=" + "x" * 43 + "&code=code&error=access_denied",
        "state=" + "x" * 43 + "&code=code&code=code",
    ],
)
async def test_invalid_callback_is_safe(browser: BrowserHarness, query: str) -> None:
    await browser.client.get("/api/v1/auth/google/start")
    response = await browser.client.get("/api/v1/auth/google/callback?" + query)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["code"] == "login_invalid"
    assert "code=code" not in response.text
    assert LOGIN_COOKIE not in browser.client.cookies


async def test_callback_failures_have_a_persistent_independent_http_limit(
    browser: BrowserHarness,
) -> None:
    client = browser.client
    for _ in range(MAX_CALLBACK_FAILURES_PER_HOUR):
        invalid = await client.get("/api/v1/auth/google/callback")
        assert invalid.status_code == HTTPStatus.BAD_REQUEST
    limited = await client.get("/api/v1/auth/google/callback")
    assert limited.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert limited.json()["code"] == "login_rate_limited"
    assert int(limited.headers["retry-after"]) > 0
    assert limited.json()["recovery"]["retry_at"]
    navigation = await client.get("/api/v1/auth/google/callback", headers={"Accept": "text/html"})
    assert navigation.status_code == HTTPStatus.SEE_OTHER
    assert navigation.headers["x-auth-error-status"] == "429"
    assert int(navigation.headers["retry-after"]) > 0
    assert parse_qs(urlsplit(navigation.headers["location"]).query)["auth_error"] == [
        "login_rate_limited"
    ]
    assert SESSION_COOKIE not in client.cookies
    assert LOGIN_COOKIE not in client.cookies
    assert (await client.get("/api/v1/auth/google/start")).status_code == HTTPStatus.SEE_OTHER


async def test_provider_cancel_and_outage_have_distinct_safe_recovery(
    browser: BrowserHarness,
) -> None:
    client = browser.client
    started = await client.get("/api/v1/auth/google/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    cancelled = await client.get(
        "/api/v1/auth/google/callback", params={"state": state, "error": "access_denied"}
    )
    assert cancelled.status_code == HTTPStatus.BAD_REQUEST
    assert SESSION_COOKIE not in client.cookies
    started = await client.get("/api/v1/auth/google/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    browser.provider.unavailable = True
    unavailable = await client.get(
        "/api/v1/auth/google/callback", params={"state": state, "code": "code"}
    )
    assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert unavailable.json()["code"] == "login_provider_unavailable"
    assert SESSION_COOKIE not in client.cookies


async def test_start_never_accepts_external_redirect(browser: BrowserHarness) -> None:
    response = await browser.client.get(
        "/api/v1/auth/google/start", params={"return_to": "https://evil.example"}
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "location" not in response.headers


async def test_second_start_invalidates_first_browser_flow(browser: BrowserHarness) -> None:
    client = browser.client
    first = await client.get("/api/v1/auth/google/start")
    first_browser = client.cookies[LOGIN_COOKIE]
    first_state = parse_qs(urlsplit(first.headers["location"]).query)["state"][0]
    second = await client.get("/api/v1/auth/google/start")
    assert second.status_code == HTTPStatus.SEE_OTHER
    client.cookies.set(LOGIN_COOKIE, first_browser, domain="app.test", path="/")
    rejected = await client.get(
        "/api/v1/auth/google/callback", params={"state": first_state, "code": "code"}
    )
    assert rejected.status_code == HTTPStatus.BAD_REQUEST


class VerificationSender:
    def __init__(self) -> None:
        self.messages: list[VerificationEmail] = []

    async def send(self, message: VerificationEmail, delivery_id: UUID) -> None:
        assert delivery_id.int > 0
        self.messages.append(message)


async def test_full_google_mail_verification_path_never_creates_an_extra_session(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    client = browser.client
    await login(client)
    headers = await write_headers(client)
    response = await client.post(
        "/api/v1/auth/email-challenges", json={"email": " TP@MAIL.APU.EDU.MY "}, headers=headers
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    created = ChallengeResponse.model_validate(response.json())
    resumed = IdentityResponse.model_validate((await client.get("/api/v1/me")).json())
    assert resumed.email_challenge_id == created.id
    status_url = f"/api/v1/auth/email-challenges/{created.id}"
    queued = await client.get(status_url)
    assert queued.headers["cache-control"] == "no-store"
    pending = ChallengeStatusResponse.model_validate(queued.json())
    assert pending.email == "tp@mail.apu.edu.my"
    assert pending.delivery == "queued"
    assert pending.can_verify
    assert not pending.can_resend
    assert pending.attempts_remaining == MAX_CODE_ATTEMPTS
    assert pending.verification_outcome is None
    repeated = await client.post(
        "/api/v1/auth/email-challenges", json={"email": "tp@mail.apu.edu.my"}, headers=headers
    )
    assert ChallengeResponse.model_validate(repeated.json()) == created
    sender = VerificationSender()
    cipher = AeadEmailVault(bytes.fromhex("03" * 32), bytes.fromhex("01" * 32))
    worker = DeliverVerificationEmail(
        SqlEmailWorkerUnitOfWork(async_sessionmaker(identity_engine)), sender, cipher
    )
    assert await worker() == DeliveryStep.DELIVERED
    assert len(sender.messages) == 1
    sent = ChallengeStatusResponse.model_validate((await client.get(status_url)).json())
    assert sent.delivery == "sent"
    code = sender.messages[0].code.value
    verify_headers = await write_headers(client)
    verified = await client.post(
        f"/api/v1/auth/email-challenges/{created.id}/verify",
        json={"code": code},
        headers=verify_headers,
    )
    assert verified.status_code == HTTPStatus.OK
    assert VerificationResponse.model_validate(verified.json()).verified_at is not None
    repeated_verify = await client.post(
        f"/api/v1/auth/email-challenges/{created.id}/verify",
        json={"code": code},
        headers=verify_headers,
    )
    assert repeated_verify.json() == verified.json()
    bootstrap = IdentityResponse.model_validate((await client.get("/api/v1/me")).json())
    assert bootstrap.membership_status == "verified"
    assert bootstrap.email_challenge_id is None
    completed = ChallengeStatusResponse.model_validate((await client.get(status_url)).json())
    assert completed.state == "consumed"
    assert completed.verification_outcome == "verified"
    assert not completed.can_verify
    assert not completed.can_resend
    assert bootstrap.capabilities.can_begin_onboarding
    assert not bootstrap.capabilities.can_use_student_features
    recorded = [
        json.loads(SafeJsonFormatter().format(record))
        for record in caplog.records
        if record.name == "studymate.http"
    ]
    assert any(entry.get("account_id") == str(bootstrap.account_id) for entry in recorded)
    async with async_sessionmaker(identity_engine)() as session:
        assert (await session.scalars(select(func.count()).select_from(SessionRecord))).one() == 1


async def test_challenge_status_is_bound_to_original_session(browser: BrowserHarness) -> None:
    client = browser.client
    unknown = f"/api/v1/auth/email-challenges/{uuid4()}"
    assert (await client.get(unknown)).status_code == HTTPStatus.UNAUTHORIZED
    await login(client)
    created = await client.post(
        "/api/v1/auth/email-challenges",
        json={"email": "tp@mail.apu.edu.my"},
        headers=await write_headers(client),
    )
    challenge = ChallengeResponse.model_validate(created.json())
    assert (await client.get(unknown)).status_code == HTTPStatus.NOT_FOUND
    await login(client)
    resumed = IdentityResponse.model_validate((await client.get("/api/v1/me")).json())
    assert resumed.email_challenge_id is None
    denied = await client.get(f"/api/v1/auth/email-challenges/{challenge.id}")
    assert denied.status_code == HTTPStatus.NOT_FOUND
    assert "tp@mail.apu.edu.my" not in denied.text


class RejectingVerificationSender:
    async def send(self, message: VerificationEmail, delivery_id: UUID) -> None:
        assert message.code.value
        assert delivery_id.int > 0
        raise PermanentEmailError


async def test_terminal_delivery_failure_is_visible_without_disabling_verification(
    browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    client = browser.client
    await login(client)
    started = await client.post(
        "/api/v1/auth/email-challenges",
        json={"email": "tp@mail.apu.edu.my"},
        headers=await write_headers(client),
    )
    challenge = ChallengeResponse.model_validate(started.json())
    worker = DeliverVerificationEmail(
        SqlEmailWorkerUnitOfWork(async_sessionmaker(identity_engine)),
        RejectingVerificationSender(),
        AeadEmailVault(bytes.fromhex("03" * 32), bytes.fromhex("01" * 32)),
    )
    assert await worker() == DeliveryStep.FAILED
    response = await client.get(f"/api/v1/auth/email-challenges/{challenge.id}")
    assert response.status_code == HTTPStatus.OK
    failed = ChallengeStatusResponse.model_validate(response.json())
    assert failed.delivery == "failed"
    assert failed.state == "active"
    assert failed.can_verify
    assert not failed.can_resend
    assert failed.verification_outcome is None
    assert "provider_rejected" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "sensitive-invalid-code"},
        {"code": "123456", "extra": "private-message"},
        {},
    ],
)
async def test_validation_does_not_echo_otp_or_private_input(
    browser: BrowserHarness, payload: dict[str, str]
) -> None:
    await login(browser.client)
    response = await browser.client.post(
        f"/api/v1/auth/email-challenges/{uuid4()}/verify",
        json=payload,
        headers=await write_headers(browser.client),
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "sensitive-invalid-code" not in response.text
    assert "private-message" not in response.text
    assert "123456" not in response.text
    assert response.json()["code"] == "invalid_fields"


async def test_institutional_start_security_and_safe_failure_codes(browser: BrowserHarness) -> None:
    client = browser.client
    response = await client.post(
        "/api/v1/auth/email-challenges",
        json={"email": "tp@mail.apu.edu.my"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    await login(client)
    headers = await write_headers(client)
    response = await client.post(
        "/api/v1/auth/email-challenges",
        json={"email": "tp@mail.apu.edu.my"},
        headers={
            "Origin": "https://evil.example",
            "X-CSRF-Token": headers["X-CSRF-Token"],
            "Idempotency-Key": headers["Idempotency-Key"],
        },
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()["code"] == "origin_denied"
    response = await client.post(
        "/api/v1/auth/email-challenges",
        json={"email": "tp@mail.apu.edu.my"},
        headers={"Origin": ORIGIN, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == HTTPStatus.FORBIDDEN
    response = await client.post(
        "/api/v1/auth/email-challenges", json={"email": "person@gmail.com"}, headers=headers
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "person@gmail.com" not in response.text
    response = await client.post(
        "/api/v1/auth/email-challenges", json={"email": "tp@mail.apu.edu.my"}, headers=headers
    )
    assert response.status_code == HTTPStatus.ACCEPTED
    conflict = await client.post(
        "/api/v1/auth/email-challenges", json={"email": "other@mail.apu.edu.my"}, headers=headers
    )
    assert conflict.status_code == HTTPStatus.CONFLICT
    headers["Idempotency-Key"] = str(uuid4())
    rate_limited = await client.post(
        "/api/v1/auth/email-challenges", json={"email": "tp@mail.apu.edu.my"}, headers=headers
    )
    assert rate_limited.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert int(rate_limited.headers["Retry-After"]) > 0


async def test_auth_body_is_bounded_and_requires_json(browser: BrowserHarness) -> None:
    client = browser.client
    unsupported = await client.post(
        "/api/v1/auth/email-challenges", content=b"email=tp@mail.apu.edu.my"
    )
    assert unsupported.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    oversized = await client.post(
        "/api/v1/auth/email-challenges",
        content=b"x" * (COMMAND_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


@pytest.mark.parametrize("outcome", ["invalid", "cancelled", "unavailable", "success"])
async def test_browser_callback_outcomes_are_bounded(browser: BrowserHarness, outcome: str) -> None:
    client = browser.client
    started = await client.get("/api/v1/auth/google/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    params = {"state": state, "code": "code", "next": "https://evil.test"}
    if outcome == "invalid":
        params["state"] = "x" * 43
    elif outcome == "cancelled":
        del params["code"]
        params["error"] = "access_denied"
    elif outcome == "unavailable":
        browser.provider.unavailable = True
    response = await client.get(
        "/api/v1/auth/google/callback", params=params, headers={"Accept": "text/html"}
    )
    assert response.status_code == HTTPStatus.SEE_OTHER
    location = urlsplit(response.headers["location"])
    assert location.scheme + "://" + location.netloc == ORIGIN
    assert location.path == "/onboarding"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert LOGIN_COOKIE not in client.cookies
    if outcome == "success":
        assert not location.query
        assert SESSION_COOKIE in client.cookies
    else:
        query = parse_qs(location.query)
        expected = {
            "invalid": ("login_invalid", "400"),
            "cancelled": ("login_cancelled", "400"),
            "unavailable": ("login_provider_unavailable", "503"),
        }
        assert set(query) == {"auth_error", "auth_ref"}
        assert query["auth_error"] == [expected[outcome][0]]
        assert query["auth_ref"] == [response.headers["x-request-id"]]
        UUID(query["auth_ref"][0])
        assert response.headers["x-auth-error-status"] == expected[outcome][1]
        assert SESSION_COOKIE not in client.cookies
        assert "private-code" not in response.headers["location"]
        assert "evil.test" not in response.headers["location"]


async def test_untrusted_cancellation_is_not_confirmed(browser: BrowserHarness) -> None:
    response = await browser.client.get(
        "/api/v1/auth/google/callback",
        params={"state": "x" * 43, "error": "access_denied"},
        headers={"Accept": "text/html"},
    )
    assert parse_qs(urlsplit(response.headers["location"]).query)["auth_error"] == ["login_invalid"]
