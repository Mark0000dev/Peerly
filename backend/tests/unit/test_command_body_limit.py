import asyncio
from collections.abc import AsyncIterator
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from studymate.presentation.command_body_limit import JsonCommandBodyLimit


class CommandHandler:
    def __init__(self) -> None:
        self.bodies: list[bytes] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.bodies.append(await Request(scope, receive).body())
        await Response(status_code=204)(scope, receive, send)


@pytest.mark.parametrize(
    ("path", "body", "content_type", "status"),
    [
        ("/api/v1/operator/accounts/person/photo-reviews", b"{}", "text/plain", 415),
        ("/api/v1/operator/accounts/person/photo-reviews", b"x" * 8193, "application/json", 413),
        ("/api/v1/operator/accounts/person/photo-reviews", b"{}", "application/json", 204),
        ("/api/v1/operator/reports/report/reviews", b"{}", "text/plain", 415),
        ("/api/v1/operator/reports/report/reviews", b"x" * 8193, "application/json", 413),
        ("/api/v1/operator/reports/report/reviews", b"{}", "application/json", 204),
        ("/api/v1/ai/jobs", b"{}", "text/plain", 415),
        ("/api/v1/reports", b"{}", "text/plain", 415),
        ("/api/v1/reports", b"x" * 8193, "application/json", 413),
        ("/api/v1/me/blocks/person", b"{}", "text/plain", 415),
        ("/api/v1/me/blocks/person", b"x" * 8193, "application/json", 413),
        ("/api/v1/discovery/passes/person", b"{}", "text/plain", 415),
        ("/api/v1/discovery/passes/person", b"x" * 8193, "application/json", 413),
        ("/api/v1/ai/jobs", b"x" * 8193, "application/json", 413),
        ("/api/v1/ai/jobs/job/cancel", b"{}", "application/json", 400),
        ("/api/v1/ai/jobs/job/cancel", b"", "", 204),
        ("/api/v1/ai/jobs", b"{}", "application/json; charset=utf-8", 204),
        ("/api/v1/operator/accounts/person/membership-verifications", b"{}", "text/plain", 415),
        (
            "/api/v1/operator/accounts/person/membership-verifications",
            b"x" * 8193,
            "application/json",
            413,
        ),
        (
            "/api/v1/operator/accounts/person/membership-verifications",
            b"{}",
            "application/json",
            204,
        ),
    ],
)
async def test_commands_bound_body_before_handler(
    path: str, body: bytes, content_type: str, status: int
) -> None:
    handler = CommandHandler()
    async with AsyncClient(
        transport=ASGITransport(app=JsonCommandBodyLimit(handler)), base_url="https://test"
    ) as client:
        response = await client.post(path, content=body, headers={"content-type": content_type})
    assert response.status_code == status
    if status == HTTPStatus.NO_CONTENT:
        assert handler.bodies == [body]
    else:
        assert not handler.bodies
        assert response.json()["code"] == "command_body_rejected"
        assert response.headers["cache-control"] == "no-store"
        assert "x" * 100 not in response.text


async def test_chunked_ai_body_cannot_bypass_limit() -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"x" * 4096
        yield b"x" * 4096
        yield b"x"

    handler = CommandHandler()
    async with AsyncClient(
        transport=ASGITransport(app=JsonCommandBodyLimit(handler)), base_url="https://test"
    ) as client:
        response = await client.post(
            "/api/v1/ai/jobs", content=chunks(), headers={"content-type": "application/json"}
        )
    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert not handler.bodies


async def test_slow_ai_body_times_out_before_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("studymate.presentation.command_body_limit.BODY_TIMEOUT_SECONDS", 0.01)

    async def slow_body() -> AsyncIterator[bytes]:
        yield b"{"
        await asyncio.sleep(1)
        yield b"}"

    handler = CommandHandler()
    async with AsyncClient(
        transport=ASGITransport(app=JsonCommandBodyLimit(handler)), base_url="https://test"
    ) as client:
        response = await client.post(
            "/api/v1/ai/jobs", content=slow_body(), headers={"content-type": "application/json"}
        )
    assert response.status_code == HTTPStatus.REQUEST_TIMEOUT
    assert not handler.bodies


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", "/api/v1/operator/accounts/invalid-uuid/ban"),
        ("POST", "/api/v1/me/deletion"),
    ],
)
@pytest.mark.parametrize(
    ("body", "content_type", "status"),
    [(b"x" * 8193, "application/json", 413), (b"{}", "text/plain", 415)],
)
async def test_lifecycle_mutation_body_rejection_precedes_authority_and_uuid_parsing(
    method: str, path: str, body: bytes, content_type: str, status: int
) -> None:
    handler = CommandHandler()
    async with AsyncClient(
        transport=ASGITransport(app=JsonCommandBodyLimit(handler)), base_url="https://test"
    ) as client:
        response = await client.request(
            method, path, content=body, headers={"content-type": content_type}
        )
    assert response.status_code == status
    assert response.json()["code"] == "command_body_rejected"
    assert not handler.bodies


@pytest.mark.parametrize(
    "path",
    ["/api/v1/operator/accounts/person/ban", "/api/v1/me/deletion"],
)
async def test_slow_lifecycle_json_never_reaches_handler(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.setattr("studymate.presentation.command_body_limit.BODY_TIMEOUT_SECONDS", 0.01)

    async def slow_body() -> AsyncIterator[bytes]:
        yield b"{"
        await asyncio.Event().wait()

    handler = CommandHandler()
    async with AsyncClient(
        transport=ASGITransport(app=JsonCommandBodyLimit(handler)), base_url="https://test"
    ) as client:
        response = await client.request(
            "PUT" if path.endswith("/ban") else "POST",
            path,
            content=slow_body(),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == HTTPStatus.REQUEST_TIMEOUT
    assert response.json()["code"] == "command_body_rejected"
    assert not handler.bodies
