"""Real PostgreSQL acceptance; run with existing migrated identity_engine fixture."""

import asyncio
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.native_login import (
    BindNativeCallback,
    ExchangeNativeAttempt,
    NativeLoginRejectedError,
    RegisterNativeAttempt,
    proof_challenge,
)
from studymate.application.identity.sessions import SessionCredential
from studymate.infrastructure.persistence.identity_models import AccountRecord, SessionRecord
from studymate.infrastructure.persistence.native_login import (
    NativeAttemptRecord,
    SqlNativeUnitOfWork,
)
from studymate.infrastructure.security.login_vault import AeadLoginVault
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.identity import LOGIN_COOKIE, IdentityResponse
from tests.integration.http_identity import ORIGIN, BrowserHarness, login

pytestmark = pytest.mark.integration
VERIFIER = "A" * 43
HASHER = Sha256SessionHasher()


async def pending(engine: AsyncEngine) -> tuple[SqlNativeUnitOfWork, UUID, SessionCredential]:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uow = SqlNativeUnitOfWork(sessions)
    vault = AeadLoginVault(bytes(range(32)))
    browser = await vault.session_credential()
    credential = await vault.session_credential()
    attempt_id = uuid4()
    now = datetime.now(UTC)
    async with sessions.begin() as session:
        account = uuid4()
        session.add(AccountRecord(id=account, created_at=now))
        await session.flush()
        session.add(
            SessionRecord(
                id=uuid4(),
                account_id=account,
                secret_digest=await HASHER.digest(credential),
                issued_at=now,
                expires_at=now + timedelta(days=7),
            )
        )
    await RegisterNativeAttempt(uow, HASHER)(attempt_id, proof_challenge(VERIFIER), browser)
    assert await BindNativeCallback(uow, HASHER)(browser, credential)
    return uow, attempt_id, credential


async def test_pg_one_concurrent_exchange_winner(identity_engine: AsyncEngine) -> None:
    uow, attempt_id, provisional = await pending(identity_engine)
    exchange = ExchangeNativeAttempt(uow, HASHER, AeadLoginVault(bytes(range(32))))
    results = await asyncio.gather(
        exchange(attempt_id, VERIFIER), exchange(attempt_id, VERIFIER), return_exceptions=True
    )
    assert sum(isinstance(result, SessionCredential) for result in results) == 1
    assert sum(isinstance(result, NativeLoginRejectedError) for result in results) == 1
    async with uow.sessions() as session:
        row = (
            await session.scalars(
                select(SessionRecord).where(
                    SessionRecord.secret_digest == await HASHER.digest(provisional)
                )
            )
        ).one()
        assert row.revoked_at is not None
        attempt = await session.get(NativeAttemptRecord, attempt_id)
        assert attempt is not None
        assert attempt.consumed_at is not None
        assert row.expires_at <= attempt.expires_at


async def test_pg_revocation_before_exchange_denies_native_authority(
    identity_engine: AsyncEngine,
) -> None:
    uow, attempt_id, provisional = await pending(identity_engine)
    async with uow.sessions.begin() as session:
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.secret_digest == await HASHER.digest(provisional))
            .values(revoked_at=datetime.now(UTC))
        )
    exchange = ExchangeNativeAttempt(uow, HASHER, AeadLoginVault(bytes(range(32))))
    with pytest.raises(NativeLoginRejectedError):
        await exchange(attempt_id, VERIFIER)
    async with uow.sessions() as session:
        attempt = await session.get(NativeAttemptRecord, attempt_id)
        assert attempt is not None
        assert attempt.consumed_at is None


async def test_pg_http_native_exchange_keeps_browser_session_and_requires_real_membership(
    browser: BrowserHarness,
) -> None:
    client = browser.client
    await login(client)
    browser_session = client.cookies[SESSION_COOKIE]
    attempt_id = str(uuid4())
    started = await client.get(
        "/api/v1/auth/native/start",
        params={"attempt_id": attempt_id, "challenge": proof_challenge(VERIFIER)},
    )
    assert started.status_code == HTTPStatus.SEE_OTHER
    assert LOGIN_COOKIE in client.cookies  # Issued by start in the external browser jar.
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    callback = await client.get(
        "/api/v1/auth/google/callback", params={"state": state, "code": "code"}
    )
    assert callback.status_code == HTTPStatus.SEE_OTHER
    assert callback.headers["location"] == ORIGIN + "/api/v1/auth/native/return"
    assert client.cookies[SESSION_COOKIE] == browser_session
    assert (await client.get("/api/v1/me")).status_code == HTTPStatus.OK
    async with AsyncClient(transport=ASGITransport(app=browser.app), base_url=ORIGIN) as native:
        # A distinct native jar has neither browser binding nor a session to copy.
        assert not list(native.cookies)
        assert (await native.get("/api/v1/me")).status_code == HTTPStatus.UNAUTHORIZED
        proof = {"attempt_id": attempt_id, "verifier": VERIFIER}
        assert (
            await native.post("/api/v1/auth/native/exchange", json=proof)
        ).status_code == HTTPStatus.FORBIDDEN
        exchange = await native.post(
            "/api/v1/auth/native/exchange", json=proof, headers={"Origin": ORIGIN}
        )
        assert exchange.status_code == HTTPStatus.NO_CONTENT
        assert exchange.content == b""
        assert LOGIN_COOKIE not in native.cookies
        assert client.cookies[SESSION_COOKIE] == browser_session
        assert native.cookies[SESSION_COOKIE] != browser_session
        me = await native.get("/api/v1/me")
        assert me.status_code == HTTPStatus.OK
        identity = IdentityResponse.model_validate(me.json())
        assert identity.membership_status == "unverified"
        assert not identity.capabilities.can_use_student_features
        assert (await client.get("/api/v1/me")).status_code == HTTPStatus.OK
