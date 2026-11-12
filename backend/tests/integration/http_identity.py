from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx2
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import studymate.bootstrap as bootstrap_module
from studymate.application.identity.google import (
    GoogleAuthorization,
    GoogleCode,
    GoogleUnavailableError,
)
from studymate.application.media.storage import MediaStorage
from studymate.bootstrap import create_app
from studymate.config import (
    AiHttpConfiguration,
    AuthenticationConfiguration,
    MediaConfiguration,
    Settings,
)
from studymate.domain.membership import GOOGLE_ISSUER, GoogleIdentity
from studymate.infrastructure.identity.google import GoogleConfiguration
from studymate.infrastructure.persistence.identity_models import InstitutionalBindingRecord
from studymate.presentation.identity import IdentityResponse
from tests.integration.media_fixture import Storage

ORIGIN = "https://app.test"


class GoogleBoundary:
    def __init__(self) -> None:
        self.unavailable = False

    async def authorization_url(self, authorization: GoogleAuthorization) -> str:
        return "https://accounts.google.com/?state=" + authorization.state

    async def exchange(
        self, code: GoogleCode, authorization: GoogleAuthorization
    ) -> GoogleIdentity:
        assert authorization.nonce
        assert code.value == "code"
        if self.unavailable:
            raise GoogleUnavailableError
        return GoogleIdentity(GOOGLE_ISSUER, "subject")


@dataclass(frozen=True, slots=True)
class BrowserHarness:
    client: AsyncClient
    provider: GoogleBoundary
    storage: Storage
    app: FastAPI
    ai_engine: AsyncEngine
    change_engine: AsyncEngine


@pytest.fixture
async def browser(
    identity_engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[BrowserHarness]:
    provider = GoogleBoundary()
    storage = Storage(b"")
    async with identity_engine.connect() as connection:
        schema: object = (await connection.execute(text("SELECT current_schema()"))).scalar_one()
    assert isinstance(schema, str)
    ai_engine = bootstrap_module.create_ai_admission_engine(
        database_url, server_settings={"search_path": schema}
    )
    change_engine = bootstrap_module.create_change_read_engine(
        database_url, server_settings={"search_path": schema}
    )

    original_engine_factory = create_async_engine

    def isolated_engine(
        url: str,
        *,
        pool_pre_ping: bool,
        connect_args: dict[str, object],
        **pool_options: float,
    ) -> AsyncEngine:
        assert url == database_url
        assert pool_pre_ping
        timeout = connect_args["timeout"]
        assert isinstance(timeout, (int, float))
        assert timeout > 0
        if connect_args.get("server_settings") == {"lock_timeout": "1000"}:
            assert not pool_options
            return original_engine_factory(
                url,
                pool_pre_ping=pool_pre_ping,
                connect_args={
                    **connect_args,
                    "server_settings": {
                        "search_path": schema,
                        "lock_timeout": "1000",
                    },
                },
            )
        if "server_settings" in connect_args:
            # Direct calls to actual named factories keep their own topology.
            # Only this explicitly isolated disposable schema is permitted.
            assert connect_args["server_settings"] == {
                "search_path": schema,
                "lock_timeout": "1000",
            }
            return original_engine_factory(
                url, pool_pre_ping=pool_pre_ping, connect_args=connect_args, **pool_options
            )
        assert not pool_options
        return identity_engine

    def isolated_ai_engine(
        url: str, *, server_settings: Mapping[str, str] | None = None
    ) -> AsyncEngine:
        assert url == database_url
        assert server_settings is None
        return ai_engine

    def isolated_change_engine(
        url: str, *, server_settings: Mapping[str, str] | None = None
    ) -> AsyncEngine:
        assert url == database_url
        assert server_settings is None
        return change_engine

    def controlled_google(
        configuration: GoogleConfiguration,
        http: httpx2.AsyncClient,
    ) -> GoogleBoundary:
        assert configuration.client_id == "client.example"
        assert configuration.redirect_uri == ORIGIN + "/api/v1/auth/google/callback"
        assert not http.is_closed
        return provider

    @asynccontextmanager
    async def controlled_storage(configuration: MediaConfiguration) -> AsyncIterator[MediaStorage]:
        assert configuration.bucket == "synthetic-bucket"
        yield storage

    monkeypatch.setattr(bootstrap_module, "_open_media_storage", controlled_storage)
    monkeypatch.setattr(bootstrap_module, "create_async_engine", isolated_engine)
    monkeypatch.setattr(bootstrap_module, "GoogleOidcProvider", controlled_google)
    monkeypatch.setattr(bootstrap_module, "create_ai_admission_engine", isolated_ai_engine)
    monkeypatch.setattr(bootstrap_module, "create_change_read_engine", isolated_change_engine)
    configuration = AuthenticationConfiguration(
        client_id="client.example",
        client_secret=SecretStr("synthetic-secret"),
        public_origin=ORIGIN,
        envelope_key=SecretStr("01" * 32),
        browser_signing_key=SecretStr("02" * 32),
        code_key=SecretStr("03" * 32),
    )
    app = create_app(
        Settings(
            _env_file=None,
            observability=None,
            ai=AiHttpConfiguration(),
            database_url=SecretStr(database_url),
            authentication=configuration,
            media=MediaConfiguration(
                endpoint_origin="https://storage.example.test",
                bucket="synthetic-bucket",
                region="us-east-1",
                access_key_id=SecretStr("synthetic-identifier"),
                secret_access_key=SecretStr("synthetic-signing-material"),
            ),
        )
    )
    try:
        async with (
            LifespanManager(app),
            AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client,
        ):
            yield BrowserHarness(client, provider, storage, app, ai_engine, change_engine)
    finally:
        # Until root SSE composition owns this engine, the fixture owns its cleanup.
        await change_engine.dispose()


async def login(client: AsyncClient) -> str:
    started = await client.get("/api/v1/auth/google/start")
    assert started.status_code == HTTPStatus.SEE_OTHER
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    response = await client.get(
        "/api/v1/auth/google/callback", params={"state": state, "code": "code"}
    )
    assert response.status_code == HTTPStatus.SEE_OTHER
    return state


async def write_headers(client: AsyncClient) -> dict[str, str]:
    bootstrap = IdentityResponse.model_validate((await client.get("/api/v1/me")).json())
    return {"Origin": ORIGIN, "X-CSRF-Token": bootstrap.csrf_token, "Idempotency-Key": str(uuid4())}


async def verified(browser: BrowserHarness, engine: AsyncEngine) -> UUID:
    await login(browser.client)
    identity = IdentityResponse.model_validate((await browser.client.get("/api/v1/me")).json())
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            InstitutionalBindingRecord(
                account_id=identity.account_id,
                email=f"synthetic-{identity.account_id.hex}@mail.apu.edu.my",
                verified_at=datetime.now(UTC),
            )
        )
    return identity.account_id
