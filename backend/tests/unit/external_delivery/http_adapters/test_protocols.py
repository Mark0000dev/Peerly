"""Provider protocol/privacy outcomes over controlled async mock transports only."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from uuid import uuid4

import httpx2 as httpx
import pytest
from tests.unit.external_delivery.http_adapters.fixtures import TOKEN, lease, telegram, umami

from studymate.application.external_delivery.worker import (
    MAX_PROVIDER_RETRY_SECONDS,
    plan_completion,
)
from studymate.domain.external_delivery.delivery import (
    DeliveryState,
    DestinationRef,
    FailureCode,
    ResultKind,
)
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.external_delivery.http_adapters import (
    ExternalHttpSender,
    target_fingerprint,
)
from studymate.infrastructure.external_delivery.http_adapters.transport import (
    MAX_BYTES,
    retry_seconds,
)

EXPECTED_MESSAGE_ID = 123
MIN_DATE_WAIT_SECONDS = 119


async def test_umami_native_shape_and_identified_event_not_session_or_dedupe_claim(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = umami()
    job = lease()
    captured: list[httpx.Request] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "cache": "PRIVATE_PROVIDER_CACHE",
                "sessionId": str(uuid4()),
                "visitId": str(uuid4()),
            },
        )

    with caplog.at_level(logging.DEBUG):
        async with httpx.MockTransport(provider) as transport:
            result = await ExternalHttpSender((config,), transport).send(job)
    assert result.kind == ResultKind.ACCEPTED
    assert result.provider_message_id is None
    request = captured[0]
    assert str(request.url) == config.origin + "/api/send"
    body: object = json.loads(request.content)
    assert isinstance(body, dict)
    assert body["type"] == "event"
    assert "server.goal.saved" in request.content.decode()
    assert str(job.source_id) in request.content.decode()
    assert b'"id":' in request.content
    assert request.headers["user-agent"] == "Peerly-Delivery/1.0"
    assert all(key not in request.headers for key in ("cookie", "authorization", "x-forwarded-for"))
    assert b"userAgent" not in request.content
    assert b'"ip"' not in request.content
    assert "PRIVATE_PROVIDER_CACHE" not in repr(result) + caplog.text


async def test_telegram_is_exact_metadata_notice_and_retains_actual_message_receipt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = telegram()
    job = lease(Sink.TELEGRAM_SUPPORT)
    requests: list[httpx.Request] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 123}})

    with caplog.at_level(logging.DEBUG):
        async with httpx.MockTransport(provider) as transport:
            result = await ExternalHttpSender((config,), transport).send(job)
    assert result.kind == ResultKind.ACCEPTED
    assert result.provider_message_id == EXPECTED_MESSAGE_ID
    body: object = json.loads(requests[0].content)
    assert isinstance(body, dict)
    assert body["chat_id"] == config.chat_id
    assert body["message_thread_id"] == config.topic_id
    assert body["link_preview_options"] == {"is_disabled": True}
    assert "parse_mode" not in body
    assert b"/operator/cases/" in requests[0].content
    assert "actor_id" not in requests[0].content.decode()
    assert TOKEN not in repr(config) + repr(result) + caplog.text
    assert "/bot" not in caplog.text


@pytest.mark.parametrize(
    ("status", "kind", "failure"),
    [
        (401, ResultKind.PERMANENT, FailureCode.CREDENTIALS),
        (403, ResultKind.PERMANENT, FailureCode.CREDENTIALS),
        (302, ResultKind.PERMANENT, FailureCode.DESTINATION),
        (404, ResultKind.PERMANENT, FailureCode.DESTINATION),
        (400, ResultKind.PERMANENT, FailureCode.PERMANENT),
        (503, ResultKind.AMBIGUOUS, FailureCode.TRANSIENT),
    ],
)
async def test_http_status_is_safe_no_redirect_retry_or_provider_error_echo(
    status: int,
    kind: ResultKind,
    failure: FailureCode,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls = 0

    async def provider(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status,
            json={
                "ok": False,
                "error_code": 429,
                "parameters": {"retry_after": 123},
                "description": "PRIVATE_PROVIDER_BODY",
            },
            headers={"location": "https://private.example.test"},
        )

    async with httpx.MockTransport(provider) as transport:
        result = await ExternalHttpSender((telegram(),), transport).send(
            lease(Sink.TELEGRAM_SUPPORT)
        )
    assert result.kind == kind
    assert result.failure == failure
    assert result.http_status == status
    assert calls == 1
    assert "PRIVATE_PROVIDER_BODY" not in repr(result) + caplog.text


async def test_telegram_429_takes_larger_instruction_and_excessive_wait_stops_early_retry() -> None:
    async def provider(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "3"},
            json={
                "ok": False,
                "error_code": 429,
                "parameters": {"retry_after": MAX_PROVIDER_RETRY_SECONDS + 5},
                "description": "PRIVATE_PROVIDER_BODY",
            },
        )

    async with httpx.MockTransport(provider) as transport:
        result = await ExternalHttpSender((telegram(),), transport).send(
            lease(Sink.TELEGRAM_SUPPORT)
        )
    assert result.failure == FailureCode.RATE_LIMITED
    assert result.retry_after_seconds is not None
    assert result.retry_after_seconds > MAX_PROVIDER_RETRY_SECONDS
    disposition = plan_completion(1, result, datetime.now(UTC))
    assert disposition.state == DeliveryState.DEAD
    assert disposition.block_sink


@pytest.mark.parametrize("body", [{"beep": "boop"}, {"cache": "private"}, [], None])
async def test_umami_ignored_or_malformed_200_never_becomes_accepted(body: object) -> None:
    async def provider(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async with httpx.MockTransport(provider) as transport:
        result = await ExternalHttpSender((umami(),), transport).send(lease())
    assert result.kind != ResultKind.ACCEPTED


@pytest.mark.parametrize("identifier", [True, 0, -1, "123", 1 << 63])
async def test_success_needs_actual_positive_bounded_telegram_message_id(
    identifier: object,
) -> None:
    async def provider(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"message_id": identifier}})

    async with httpx.MockTransport(provider) as transport:
        result = await ExternalHttpSender((telegram(),), transport).send(
            lease(Sink.TELEGRAM_SUPPORT)
        )
    assert result.kind == ResultKind.AMBIGUOUS
    assert result.failure == FailureCode.INVALID_RESPONSE


async def test_revision_mismatch_missing_credentials_and_fingerprint_never_retarget() -> None:
    async def forbidden(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not start")

    first = telegram()
    rotated = replace(first, token=TOKEN + "rotated")
    assert target_fingerprint(first) == target_fingerprint(rotated)
    assert target_fingerprint(first) != target_fingerprint(replace(first, chat_id=-100999))
    async with httpx.MockTransport(forbidden) as transport:
        sender = ExternalHttpSender((replace(first, token=None),), transport)
        missing = await sender.send(lease(Sink.TELEGRAM_SUPPORT))
        unknown = await sender.send(
            replace(
                lease(Sink.TELEGRAM_SUPPORT), destination=DestinationRef(Sink.TELEGRAM_SUPPORT, 2)
            )
        )
    assert missing.failure == FailureCode.CREDENTIALS
    assert unknown.failure == FailureCode.DESTINATION


@pytest.mark.parametrize("problem", ["connect", "read", "write", "timeout"])
async def test_network_phase_maps_honest_ambiguous_outcome_without_exception_details(
    problem: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def failed(request: httpx.Request) -> httpx.Response:
        failures = {
            "connect": httpx.ConnectError,
            "read": httpx.ReadError,
            "write": httpx.WriteError,
            "timeout": httpx.ReadTimeout,
        }
        raise failures[problem]("PRIVATE_TOKEN_BODY", request=request)

    async with httpx.MockTransport(failed) as transport:
        result = await ExternalHttpSender((telegram(),), transport).send(
            lease(Sink.TELEGRAM_SUPPORT)
        )
    assert result.kind == (ResultKind.RETRYABLE if problem == "connect" else ResultKind.AMBIGUOUS)
    assert "PRIVATE_TOKEN_BODY" not in repr(result) + caplog.text
    assert TOKEN not in caplog.text


async def test_response_limit_closes_stream_without_parsing_oversized_provider_data() -> None:
    closed = asyncio.Event()

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"x" * (MAX_BYTES + 1)
            raise AssertionError("Must not drain beyond bounded response")

        async def aclose(self) -> None:
            closed.set()

    async def provider(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=Stream())

    async with httpx.MockTransport(provider) as transport:
        result = await ExternalHttpSender((umami(),), transport).send(lease())
    assert result.failure == FailureCode.INVALID_RESPONSE
    assert closed.is_set()


async def test_cancellation_propagates_without_fabricating_receipt() -> None:
    entered = asyncio.Event()

    async def blocked(_request: httpx.Request) -> httpx.Response:
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("Unreachable")

    async with httpx.MockTransport(blocked) as transport:
        task = asyncio.create_task(ExternalHttpSender((umami(),), transport).send(lease()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_retry_header_parsing_is_bounded_and_respects_date_or_unknown() -> None:
    assert retry_seconds(True) is None
    assert retry_seconds("-1") is None
    assert retry_seconds("bad") is None
    assert retry_seconds("9" * 100) == MAX_PROVIDER_RETRY_SECONDS + 1
    future = datetime.now(UTC) + timedelta(minutes=2)
    wait = retry_seconds(format_datetime(future))
    assert wait is not None
    assert wait >= MIN_DATE_WAIT_SECONDS


async def test_total_http_deadline_is_five_seconds_without_a_response_or_internal_retry() -> None:
    entered = asyncio.Event()

    async def blocked(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"] == dict.fromkeys(
            ("connect", "read", "write", "pool"), 5
        )
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("Unreachable")

    async with httpx.MockTransport(blocked) as transport:
        async with asyncio.timeout(7):
            result = await ExternalHttpSender((umami(),), transport).send(lease())
    assert entered.is_set()
    assert result.kind == ResultKind.AMBIGUOUS
    assert result.failure == FailureCode.TIMEOUT


async def test_expired_lease_and_oversized_request_are_rejected_without_http() -> None:
    async def forbidden(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not start")

    job = lease()
    expired = replace(
        job,
        started_at=job.started_at - timedelta(minutes=2),
        lease_until=job.started_at - timedelta(minutes=1),
    )
    config = replace(telegram(), operator_origin="https://" + "x" * MAX_BYTES + ".example.test")
    async with httpx.MockTransport(forbidden) as transport:
        first = await ExternalHttpSender((umami(),), transport).send(expired)
        second = await ExternalHttpSender((config,), transport).send(lease(Sink.TELEGRAM_SUPPORT))
    assert first.failure == FailureCode.LEASE_EXPIRED
    assert second.kind == ResultKind.PERMANENT
