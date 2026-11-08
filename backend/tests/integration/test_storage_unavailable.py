from http import HTTPStatus

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.engine import make_url

from studymate.bootstrap import create_app
from studymate.config import AuthenticationConfiguration, Settings
from studymate.presentation.browser import SESSION_COOKIE

pytestmark = pytest.mark.integration


async def test_auth_storage_failure_is_safe_503_not_driver_exception(
    database_url: str, unused_tcp_port: int
) -> None:
    unavailable = make_url(database_url).set(host="127.0.0.1", port=unused_tcp_port)
    app = create_app(
        Settings(
            database_url=SecretStr(unavailable.render_as_string(hide_password=False)),
            authentication=AuthenticationConfiguration(
                client_id="synthetic-client",
                client_secret=SecretStr("synthetic-secret"),
                public_origin="https://app.test",
                code_key=SecretStr("01" * 32),
                envelope_key=SecretStr("02" * 32),
                browser_signing_key=SecretStr("03" * 32),
            ),
        )
    )
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="https://app.test") as client,
    ):
        client.cookies.set(SESSION_COOKIE, "a" * 43)
        response = await client.get("/api/v1/me")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["code"] == "storage_unavailable"
    assert "asyncpg" not in response.text
    assert "ConnectionRefused" not in response.text
    assert database_url not in response.text
