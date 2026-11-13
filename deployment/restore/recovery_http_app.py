"""Explicit synthetic root composition with denied provider HTTP and local recovered media."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from http import HTTPStatus
from unittest.mock import patch

import httpx2
from deployment.restore.recovery_http import (
    ORIGIN,
    RecoveryCase,
    RecoveryHttpError,
    RestoredMedia,
    expect,
    identity,
    read_groups,
    request,
    write_groups,
)
from httpx2 import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

import studymate.bootstrap as composition
from studymate.application.media.storage import MediaStorage
from studymate.config import AuthenticationConfiguration, MediaConfiguration, Settings
from studymate.presentation.browser import SESSION_COOKIE

TOTAL_SECONDS = 90


@dataclass(slots=True)
class DeniedProviderHttp:
    attempts: int = 0

    def reject(self, request: httpx2.Request) -> httpx2.Response:
        del request
        self.attempts += 1
        raise RecoveryHttpError("external_provider_attempt")


def configuration(engine: AsyncEngine) -> Settings:
    return Settings(
        _env_file=None,
        observability=None,
        database_url=SecretStr(engine.url.render_as_string(hide_password=False)),
        authentication=AuthenticationConfiguration(
            client_id="recovery.invalid",
            client_secret=SecretStr("synthetic-unused-client-secret"),
            public_origin=ORIGIN,
            envelope_key=SecretStr("01" * 32),
            browser_signing_key=SecretStr("02" * 32),
            code_key=SecretStr("03" * 32),
        ),
        media=MediaConfiguration(
            endpoint_origin="https://storage.invalid",
            bucket="synthetic-recovery",
            region="us-east-1",
            access_key_id=SecretStr("synthetic-unused-access"),
            secret_access_key=SecretStr("synthetic-unused-secret"),
        ),
    )


async def run_http(
    engine: AsyncEngine, case: RecoveryCase, media: RestoredMedia
) -> dict[str, object]:
    case.guard(engine)
    async with asyncio.timeout(5), engine.connect() as connection:
        expect(
            await connection.scalar(text("SELECT current_database()")) == case.target, "database"
        )
    denied = DeniedProviderHttp()
    native_client = httpx2.AsyncClient

    def provider_client(
        *, timeout: float, limits: httpx2.Limits, follow_redirects: bool
    ) -> httpx2.AsyncClient:
        return native_client(
            timeout=timeout,
            limits=limits,
            follow_redirects=follow_redirects,
            transport=httpx2.MockTransport(denied.reject),
            trust_env=False,
        )

    @asynccontextmanager
    async def restored_storage(config: MediaConfiguration) -> AsyncIterator[MediaStorage]:
        expect(config.bucket == "synthetic-recovery", "media_fixture_config")
        yield media

    with (
        patch.object(composition, "_open_media_storage", restored_storage),
        patch.object(httpx2, "AsyncClient", provider_client),
    ):
        async with asyncio.timeout(TOTAL_SECONDS):
            app = composition.create_app(configuration(engine))
            async with app.router.lifespan_context(app), AsyncExitStack() as stack:
                clients: dict[str, AsyncClient] = {}
                principals = {
                    "owner": case.owner,
                    "other": case.other,
                    "operator": case.operator,
                    "expired": case.expired,
                    "revoked": case.revoked,
                    "deleted": case.deleted,
                    "revoked_operator": case.revoked_operator,
                }
                for name in (*principals, "anonymous", "malformed"):
                    client = await stack.enter_async_context(
                        AsyncClient(
                            transport=ASGITransport(app=app),
                            base_url=ORIGIN,
                            timeout=5,
                            trust_env=False,
                            follow_redirects=False,
                        )
                    )
                    if name in principals:
                        client.cookies.set(
                            SESSION_COOKIE,
                            principals[name].credential.value,
                            domain="recovery.invalid",
                            path="/",
                        )
                    elif name == "malformed":
                        client.cookies.set(
                            SESSION_COOKIE, "invalid-cookie", domain="recovery.invalid", path="/"
                        )
                    clients[name] = client
                me = await read_groups(case, engine, clients, media)
                await write_groups(case, engine, clients["owner"], me)
                await identity(clients["other"], case.other)
            # A new app/lifespan and cookie jar must observe committed revocation.
            restarted = composition.create_app(configuration(engine))
            async with (
                restarted.router.lifespan_context(restarted),
                AsyncClient(
                    transport=ASGITransport(app=restarted),
                    base_url=ORIGIN,
                    trust_env=False,
                ) as client,
            ):
                client.cookies.set(
                    SESSION_COOKIE, case.owner.credential.value, domain="recovery.invalid", path="/"
                )
                await request(client, "GET", "/api/v1/me", HTTPStatus.UNAUTHORIZED)
                client.cookies.clear()
                client.cookies.set(
                    SESSION_COOKIE, case.other.credential.value, domain="recovery.invalid", path="/"
                )
                await identity(client, case.other)
    expect(denied.attempts == 0, "provider_http_attempted")
    return {
        "status": "synthetic_restored_root_http_contracts",
        "scenario_groups": 6,
        "provider_http_attempts": denied.attempts,
        "restored_media_reads": media.reads,
        "transport": "httpx_asgi_full_application_lifespan",
        "tcp_tls_browser_proven": False,
        "full_restore_proven": False,
    }
