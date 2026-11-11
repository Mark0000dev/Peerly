"""Two exact registered destinations; return only closed, safe provider outcomes."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from types import MappingProxyType
from typing import TYPE_CHECKING
from uuid import UUID

import httpx2 as httpx

from studymate.domain.external_delivery.delivery import (
    MAX_PROVIDER_MESSAGE_ID,
    DeliveryLease,
    DeliveryResult,
    DestinationRef,
    FailureCode,
    ResultKind,
    UmamiEvent,
)
from studymate.infrastructure.external_delivery.http_adapters.configuration import (
    DestinationConfig,
    UmamiConfig,
)
from studymate.infrastructure.external_delivery.http_adapters.projections import (
    telegram_payload,
    umami_payload,
)
from studymate.infrastructure.external_delivery.http_adapters.transport import (
    HttpReply,
    parse_object,
    post,
    retry_seconds,
    status_result,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def invalid_response(status: int) -> DeliveryResult:
    return DeliveryResult(ResultKind.AMBIGUOUS, FailureCode.INVALID_RESPONSE, status)


def umami_result(reply: HttpReply) -> DeliveryResult:
    rejected = status_result(reply)
    if rejected is not None:
        return rejected
    body = parse_object(reply.body)
    if body is None:
        return invalid_response(reply.status)
    if body.get("beep") == "boop":
        return DeliveryResult(ResultKind.PERMANENT, FailureCode.DESTINATION, reply.status)
    cache, session, visit = body.get("cache"), body.get("sessionId"), body.get("visitId")
    if (
        not isinstance(cache, str)
        or not cache
        or not isinstance(session, str)
        or not isinstance(visit, str)
    ):
        return invalid_response(reply.status)
    try:
        UUID(session)
        UUID(visit)
    except ValueError:
        return invalid_response(reply.status)
    # Cache is sensitive transport state, not a delivery identifier or persisted metadata.
    return DeliveryResult(ResultKind.ACCEPTED, http_status=reply.status)


MAX_TOKEN_CHARACTERS = 512


def telegram_error(code: object, status: int) -> DeliveryResult:
    if type(code) is int and code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        return DeliveryResult(ResultKind.PERMANENT, FailureCode.CREDENTIALS, status)
    if type(code) is int and code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return DeliveryResult(ResultKind.AMBIGUOUS, FailureCode.TRANSIENT, status)
    return DeliveryResult(ResultKind.PERMANENT, FailureCode.PERMANENT, status)


def telegram_result(reply: HttpReply) -> DeliveryResult:
    rejected = status_result(reply)
    # A proxy/server5xx cannot be downgraded to a definite rejection by a
    # contradictory provider body. Only actual429 may refine its cooldown.
    if rejected is not None and reply.status != HTTPStatus.TOO_MANY_REQUESTS:
        return rejected
    body = parse_object(reply.body)
    if body is None:
        return rejected or invalid_response(reply.status)
    code = body.get("error_code")
    if reply.status == HTTPStatus.TOO_MANY_REQUESTS or (
        type(code) is int and code == HTTPStatus.TOO_MANY_REQUESTS and body.get("ok") is False
    ):
        parameters = body.get("parameters")
        wait = (
            retry_seconds(parameters.get("retry_after")) if isinstance(parameters, dict) else None
        )
        values = [value for value in (wait, retry_seconds(reply.retry_after)) if value is not None]
        return DeliveryResult(
            ResultKind.RETRYABLE,
            FailureCode.RATE_LIMITED,
            reply.status,
            retry_after_seconds=max(values) if values else None,
        )
    if body.get("ok") is False:
        return telegram_error(code, reply.status)
    result = body.get("result")
    identifier = result.get("message_id") if isinstance(result, dict) else None
    if (
        body.get("ok") is not True
        or type(identifier) is not int
        or not 1 <= identifier <= MAX_PROVIDER_MESSAGE_ID
    ):
        return invalid_response(reply.status)
    return DeliveryResult(
        ResultKind.ACCEPTED, http_status=reply.status, provider_message_id=identifier
    )


@dataclass(frozen=True, slots=True)
class ExternalHttpSender:
    configurations: tuple[DestinationConfig, ...] = field(repr=False)
    transport: httpx.AsyncBaseTransport = field(repr=False)
    _destinations: "Mapping[DestinationRef, DestinationConfig]" = field(init=False, repr=False)

    def __post_init__(self) -> None:
        values = {configuration.destination: configuration for configuration in self.configurations}
        if len(values) != len(self.configurations):
            raise ValueError("Duplicate external destination revision")
        object.__setattr__(self, "_destinations", MappingProxyType(values))

    async def send(self, lease: DeliveryLease) -> DeliveryResult:
        remaining = (lease.lease_until - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return DeliveryResult(ResultKind.AMBIGUOUS, FailureCode.LEASE_EXPIRED)
        configuration = self._destinations.get(lease.destination)
        if configuration is None:
            return DeliveryResult(ResultKind.PERMANENT, FailureCode.DESTINATION)
        if isinstance(configuration, UmamiConfig):
            if (
                not isinstance(lease.payload, UmamiEvent)
                or lease.payload.source.id != lease.source_id
            ):
                return DeliveryResult(ResultKind.PERMANENT, FailureCode.PERMANENT)
            result = await post(
                self.transport,
                configuration.origin + "/api/send",
                umami_payload(lease, configuration),
                seconds=remaining,
            )
            return result if isinstance(result, DeliveryResult) else umami_result(result)
        token = configuration.token
        if (
            token is None
            or len(token) > MAX_TOKEN_CHARACTERS
            or re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{1,256}", token) is None
        ):
            return DeliveryResult(ResultKind.PERMANENT, FailureCode.CREDENTIALS)
        reply = await post(
            self.transport,
            "https://api.telegram.org/bot" + token + "/sendMessage",
            telegram_payload(lease, configuration),
            seconds=remaining,
        )
        return reply if isinstance(reply, DeliveryResult) else telegram_result(reply)
