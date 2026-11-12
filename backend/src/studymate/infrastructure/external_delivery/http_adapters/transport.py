"""Single bounded POST over injected transport, without client URL logging or retries."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from math import ceil

import httpx2 as httpx

from studymate.application.external_delivery.worker import (
    HTTP_DEADLINE_SECONDS,
    MAX_PROVIDER_RETRY_SECONDS,
)
from studymate.domain.external_delivery.delivery import DeliveryResult, FailureCode, ResultKind
from studymate.infrastructure.external_delivery.http_adapters.projections import Json

MAX_BYTES = 16 * 1024
MAX_RETRY_DIGITS = 10
MAX_RETRY_HEADER = 128
USER_AGENT = "Peerly-Delivery/1.0"
UMAMI_USER_AGENT = "Peerly/1.0 (application event relay; automated service, no browser identity)"


@dataclass(frozen=True, slots=True)
class HttpReply:
    status: int
    retry_after: str | None = field(repr=False)
    body: bytes | None = field(repr=False)


def retry_seconds(value: object) -> int | None:
    if type(value) is int:
        return min(value, MAX_PROVIDER_RETRY_SECONDS + 1) if value > 0 else None
    if not isinstance(value, str) or len(value) > MAX_RETRY_HEADER:
        return None
    if value.isascii() and value.isdecimal():
        number = MAX_PROVIDER_RETRY_SECONDS + 1 if len(value) > MAX_RETRY_DIGITS else int(value)
        return retry_seconds(number)
    try:
        at = parsedate_to_datetime(value)
        if at.tzinfo is None:
            return None
        return retry_seconds(ceil((at - datetime.now(UTC)).total_seconds()))
    except (ValueError, TypeError, OverflowError):
        return None


def parse_object(body: bytes | None) -> dict[str, object] | None:
    if body is None:
        return None
    try:
        value: object = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        return None
    if not isinstance(value, dict):
        return None
    return {key: item for key, item in value.items() if isinstance(key, str)}


async def read_reply(response: httpx.Response) -> HttpReply:
    body: bytes | None = None
    try:
        if response.headers.get("content-encoding", "identity").lower() in {"", "identity"}:
            if response.is_stream_consumed:
                body = response.content if len(response.content) <= MAX_BYTES else None
            else:
                data = bytearray()
                async for chunk in response.aiter_raw(chunk_size=MAX_BYTES + 1):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        break
                if len(data) <= MAX_BYTES:
                    body = bytes(data)
        return HttpReply(response.status_code, response.headers.get("retry-after"), body)
    finally:
        await response.aclose()


async def post(
    transport: httpx.AsyncBaseTransport,
    url: str,
    payload: dict[str, Json],
    *,
    seconds: float = HTTP_DEADLINE_SECONDS,
    user_agent: str = USER_AGENT,
) -> HttpReply | DeliveryResult:
    deadline = min(HTTP_DEADLINE_SECONDS, seconds)
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()
    if len(encoded) > MAX_BYTES:
        return DeliveryResult(ResultKind.PERMANENT, FailureCode.PERMANENT)
    request = httpx.Request(
        "POST",
        url,
        content=encoded,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": user_agent,
        },
        extensions={"timeout": dict.fromkeys(("connect", "read", "write", "pool"), deadline)},
    )
    try:
        async with asyncio.timeout(deadline):
            response = await transport.handle_async_request(request)
            return await read_reply(response)
    except (httpx.ConnectTimeout, httpx.PoolTimeout):
        return DeliveryResult(ResultKind.RETRYABLE, FailureCode.TIMEOUT)
    except httpx.ConnectError:
        return DeliveryResult(ResultKind.RETRYABLE, FailureCode.TRANSIENT)
    except (httpx.TimeoutException, TimeoutError):
        return DeliveryResult(ResultKind.AMBIGUOUS, FailureCode.TIMEOUT)
    except httpx.TransportError:
        return DeliveryResult(ResultKind.AMBIGUOUS, FailureCode.TRANSIENT)


def status_result(reply: HttpReply) -> DeliveryResult | None:
    status = reply.status
    if status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        return DeliveryResult(ResultKind.PERMANENT, FailureCode.CREDENTIALS, status)
    if status == HTTPStatus.TOO_MANY_REQUESTS:
        return DeliveryResult(
            ResultKind.RETRYABLE,
            FailureCode.RATE_LIMITED,
            status,
            retry_after_seconds=retry_seconds(reply.retry_after),
        )
    if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return DeliveryResult(
            ResultKind.AMBIGUOUS,
            FailureCode.TRANSIENT,
            status,
            retry_after_seconds=retry_seconds(reply.retry_after),
        )
    if (
        HTTPStatus.MULTIPLE_CHOICES <= status < HTTPStatus.BAD_REQUEST
        or status == HTTPStatus.NOT_FOUND
    ):
        return DeliveryResult(ResultKind.PERMANENT, FailureCode.DESTINATION, status)
    if not HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
        return DeliveryResult(ResultKind.PERMANENT, FailureCode.PERMANENT, status)
    return None
