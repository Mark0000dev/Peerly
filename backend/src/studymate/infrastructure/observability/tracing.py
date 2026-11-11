"""Manual allowlist only: never automatic URL/query/body/exception instrumentation."""

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from http import HTTPStatus
from uuid import UUID

from opentelemetry.metrics import Counter, Histogram, Meter
from opentelemetry.trace import Span, SpanKind, StatusCode, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from studymate.application.discovery.cursors import DiscoveryView
from studymate.application.ports.http_observer import CLIENT_CANCELLED_STATUS, HttpObservation
from studymate.application.ports.http_tracing import HttpExecution, HttpSpan
from studymate.domain.discovery import DiscoveryMode
from studymate.infrastructure.observability.origin import ExecutionOrigin


@dataclass(slots=True)
class ExecutionSpan:
    execution: HttpExecution
    span: Span | None
    requests: Counter | None
    duration: Histogram | None
    account_id: UUID | None = None

    @property
    def trace_id(self) -> str | None:
        context = self.span.get_span_context() if self.span is not None else None
        return (
            format(context.trace_id, "032x") if context is not None and context.is_valid else None
        )

    @property
    def span_id(self) -> str | None:
        context = self.span.get_span_context() if self.span is not None else None
        return format(context.span_id, "016x") if context is not None and context.is_valid else None

    def completed(self, observation: HttpObservation) -> None:
        route = observation.route or "unmatched"
        attributes: dict[str, str | int] = {
            "http.request.method": observation.method,
            "http.route": route,
            "http.response.status_code": observation.status,
        }
        if self.span is not None:
            self.span.update_name(f"{observation.method} {route}")
            self.span.set_attributes(attributes)
            if (
                observation.status >= HTTPStatus.INTERNAL_SERVER_ERROR
                or observation.status == CLIENT_CANCELLED_STATUS
            ):
                self.span.set_status(StatusCode.ERROR)
        if self.requests is not None:
            self.requests.add(1, attributes)
        if self.duration is not None:
            self.duration.record(observation.duration_seconds, attributes)


_ACTIVE: ContextVar[ExecutionSpan | None] = ContextVar("execution_span", default=None)


def current_execution() -> ExecutionSpan | None:
    return _ACTIVE.get()


def current_origin() -> ExecutionOrigin | None:
    execution = _ACTIVE.get()
    if execution is None:
        return None
    return ExecutionOrigin(
        execution.execution.request_id,
        execution.execution.action_id,
        execution.trace_id,
        execution.span_id,
    )


def record_authenticated_actor(account_id: UUID) -> None:
    execution = _ACTIVE.get()
    if execution is not None:
        execution.account_id = account_id
        if execution.span is not None:
            execution.span.set_attribute("user.id", str(account_id))


def record_peer_profile_resource(
    account_id: UUID, photo_version: int, access_context_id: UUID | None = None
) -> None:
    execution = _ACTIVE.get()
    if execution is None or execution.span is None:
        return
    execution.span.set_attribute("studymate.peer.id", str(account_id))
    execution.span.set_attribute("studymate.photo.version", photo_version)
    if access_context_id is not None:
        execution.span.set_attribute("studymate.profile_access.id", str(access_context_id))


def record_discovery_query(
    mode: DiscoveryMode, view: DiscoveryView, account_ids: tuple[UUID, ...]
) -> None:
    execution = _ACTIVE.get()
    if execution is None or execution.span is None:
        return
    execution.span.set_attribute("studymate.discovery.mode", mode.value)
    execution.span.set_attribute("studymate.discovery.view", view.value)
    execution.span.set_attribute(
        "studymate.discovery.query_source_ids", tuple(str(value) for value in account_ids)
    )


class OtelHttpTracing:
    def __init__(self, tracer: Tracer | None = None, meter: Meter | None = None) -> None:
        self.tracer = tracer
        self.requests = (
            meter.create_counter("http.server.requests", unit="{request}") if meter else None
        )
        self.duration = (
            meter.create_histogram("http.server.request.duration", unit="s") if meter else None
        )

    @contextmanager
    def start(self, execution: HttpExecution) -> Iterator[HttpSpan]:
        carrier = (
            {"traceparent": execution.traceparent} if execution.traceparent is not None else {}
        )
        parent = TraceContextTextMapPropagator().extract(carrier)
        attributes: dict[str, str] = {"request.id": str(execution.request_id)}
        if execution.action_id is not None:
            attributes["action.id"] = str(execution.action_id)
        span_context = (
            self.tracer.start_as_current_span(
                f"{execution.method} request",
                context=parent,
                kind=SpanKind.SERVER,
                attributes=attributes,
                record_exception=False,
                set_status_on_exception=False,
            )
            if self.tracer is not None
            else nullcontext(None)
        )
        with span_context as span:
            current = ExecutionSpan(execution, span, self.requests, self.duration)
            token = _ACTIVE.set(current)
            try:
                yield current
            finally:
                _ACTIVE.reset(token)
