from http import HTTPStatus
from typing import NoReturn
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.bootstrap import create_app
from studymate.config import AiHttpConfiguration, AuthenticationConfiguration, Settings


async def test_root_mount_requires_cookie_without_database_or_provider_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_connection(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Unauthenticated identity inspection attempted SQL")

    monkeypatch.setattr(AsyncEngine, "connect", deny_connection)
    app = create_app(
        Settings(
            _env_file=None,
            media=None,
            ai=AiHttpConfiguration(),
            observability=None,
            database_url=SecretStr("postgresql+asyncpg://schema:synthetic@127.0.0.1:1/schema_only"),
            authentication=AuthenticationConfiguration(
                client_id="synthetic-schema-client",
                client_secret=SecretStr("synthetic-schema-secret"),
                public_origin="https://schema.invalid",
                envelope_key=SecretStr("01" * 32),
                browser_signing_key=SecretStr("02" * 32),
                code_key=SecretStr("03" * 32),
            ),
        )
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://schema.invalid") as client,
    ):
        response = await client.get(f"/api/v1/operator/accounts/{uuid4()}/identity-links")
        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.json()["code"] == "unauthenticated"
        assert "/api/v1/operator/accounts/{account_id}/identity-links" in app.openapi()["paths"]
