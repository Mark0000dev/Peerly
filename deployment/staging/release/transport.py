"""Bounded HTTPS transport; no automatic redirects/retries or secret discovery."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlsplit

import httpx
from deployment.staging.release.data import Object, RejectedError, load, require

MAX_BODY = 16 * 1024 * 1024
TIMEOUT = 20


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class Request:
    url: str
    method: str = "GET"
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None


class Http:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    def send(self, request: Request) -> Response:
        parsed = urlsplit(request.url)
        require(
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment,
            "https_endpoint",
        )
        return asyncio.run(self._send(request))

    async def _send(self, request: Request) -> Response:
        try:
            async with (
                asyncio.timeout(TIMEOUT + 5),
                httpx.AsyncClient(
                    timeout=TIMEOUT,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
                client.stream(
                    request.method, request.url, headers=dict(request.headers), content=request.body
                ) as response,
            ):
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    require(len(body) <= MAX_BODY, "http_body_limit")
                return Response(response.status_code, dict(response.headers), bytes(body))
        except (httpx.HTTPError, TimeoutError):
            raise RejectedError("transport_failed_no_retry") from None

    def document(self, request: Request) -> Object:
        response = self.send(request)
        require(response.status == HTTPStatus.OK, "http_status")
        return load(response.body)


def payload(value: Object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()
