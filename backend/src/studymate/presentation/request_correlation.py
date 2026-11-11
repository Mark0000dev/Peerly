"""Per-attempt server identity; untrusted headers never supply account identity."""

import asyncio
from contextlib import nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID, uuid4

from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from studymate.application.ports.http_observer import (
    CLIENT_CANCELLED_STATUS,
    HttpObservation,
    HttpObserver,
    RequestMethod,
)
from studymate.application.ports.http_tracing import HttpExecution, HttpSpan, HttpTracing

_REQUEST_ID: ContextVar[UUID | None] = ContextVar("request_id", default=None)
_TRACE_ID: ContextVar[str | None] = ContextVar("trace_id", default=None)
MAX_UUID_LENGTH = 36
MAX_TRACEPARENT_LENGTH = 128
REQUEST_CONTEXT_KEY = "studymate.execution"


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: UUID
    trace_id: str | None


def current_request_id() -> UUID | None:
    return _REQUEST_ID.get()


def current_trace_id() -> str | None:
    return _TRACE_ID.get()


def _traceparent(scope: Scope) -> str | None:
    values: list[bytes] = [
        value for key, value in scope.get("headers", ()) if key.lower() == b"traceparent"
    ]
    if len(values) != 1 or len(values[0]) > MAX_TRACEPARENT_LENGTH:
        return None
    try:
        return values[0].decode("ascii")
    except UnicodeDecodeError:
        return None


def _action_id(scope: Scope) -> UUID | None:
    values = [value for key, value in scope.get("headers", ()) if key.lower() == b"x-action-id"]
    if len(values) != 1 or len(values[0]) != MAX_UUID_LENGTH:
        return None
    try:
        return UUID(values[0].decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return None


def _method(value: str) -> RequestMethod:
    match value:
        case "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "HEAD" | "OPTIONS":
            return value
        case _:
            return "OTHER"


class RequestCorrelation:
    def __init__(
        self, app: ASGIApp, observer: HttpObserver, tracing: HttpTracing | None = None
    ) -> None:
        self.app = app
        self.observer = observer
        self.tracing = tracing

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4()
        execution = HttpExecution(
            request_id, _action_id(scope), _method(scope["method"]), _traceparent(scope)
        )
        span_scope = (
            self.tracing.start(execution) if self.tracing is not None else nullcontext(None)
        )
        with span_scope as span:
            await self._http(scope, receive, send, execution, span)

    async def _http(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        execution: HttpExecution,
        span: HttpSpan | None,
    ) -> None:
        request_id = execution.request_id
        token = _REQUEST_ID.set(request_id)
        trace_token = _TRACE_ID.set(span.trace_id if span is not None else None)
        scope[REQUEST_CONTEXT_KEY] = RequestContext(request_id, current_trace_id())
        started = perf_counter()
        status = 500

        async def correlated_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (name, value)
                    for name, value in message.get("headers", ())
                    if name.lower() != b"x-request-id"
                ]
                message = {
                    **message,
                    "headers": [*headers, (b"x-request-id", str(request_id).encode("ascii"))],
                }
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        except asyncio.CancelledError:
            status = CLIENT_CANCELLED_STATUS
            raise
        finally:
            try:
                route: object = scope.get("route")
                observation = HttpObservation(
                    request_id,
                    execution.action_id,
                    execution.method,
                    route.path if isinstance(route, Route) else None,
                    status,
                    max(0, perf_counter() - started),
                )
                if span is not None:
                    span.completed(observation)
                self.observer.completed(observation)
            finally:
                _TRACE_ID.reset(trace_token)
                _REQUEST_ID.reset(token)
