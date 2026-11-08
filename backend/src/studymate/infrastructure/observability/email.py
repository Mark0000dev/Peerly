"""A new consumer span per claimed attempt, linked to durable initiating context."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import perf_counter
from typing import Literal
from uuid import UUID

from opentelemetry import context, trace
from opentelemetry.context import Context
from opentelemetry.metrics import Counter, Histogram, Meter
from opentelemetry.trace import Link, Span, SpanContext, SpanKind, StatusCode, TraceFlags, Tracer

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.email_delivery import DeliveryStep
from studymate.infrastructure.observability.logging import LogEvent
from studymate.infrastructure.observability.origin import ExecutionOrigin

DeliveryOutcome = DeliveryStep | Literal["cancelled", "storage_unavailable", "unexpected_error"]


@dataclass(slots=True)
class DeliveryExecution:
    tracer: Tracer | None
    requests: Counter | None
    duration: Histogram | None
    span: Span | None = None
    token: Token[Context] | None = None
    delivery_id: UUID | None = None
    account_id: UUID | None = None
    origin: ExecutionOrigin | None = None

    def claimed(
        self, delivery_id: UUID, account_id: UUID, attempt: int, origin: ExecutionOrigin | None
    ) -> None:
        self.delivery_id, self.account_id, self.origin = delivery_id, account_id, origin
        if self.tracer is None:
            return
        attributes: dict[str, str | int] = {
            "messaging.system": "postgresql",
            "messaging.destination.name": "email_outbox",
            "messaging.message.id": str(delivery_id),
            "delivery.attempt": attempt,
            "user.id": str(account_id),
        }
        links: list[Link] = []
        if origin is not None:
            attributes["origin.request.id"] = str(origin.request_id)
            if origin.action_id is not None:
                attributes["action.id"] = str(origin.action_id)
            if origin.trace_id is not None and origin.span_id is not None:
                links.append(
                    Link(
                        SpanContext(
                            int(origin.trace_id, 16),
                            int(origin.span_id, 16),
                            True,
                            TraceFlags(TraceFlags.SAMPLED),
                        )
                    )
                )
        self.span = self.tracer.start_span(
            "email.delivery",
            context=Context(),
            kind=SpanKind.CONSUMER,
            attributes=attributes,
            links=links,
        )
        self.token = context.attach(trace.set_span_in_context(self.span, Context()))

    def completed(self, outcome: DeliveryOutcome, seconds: float) -> None:
        dimensions = {"outcome": str(outcome)}
        if self.requests is not None:
            self.requests.add(1, dimensions)
        if self.duration is not None:
            self.duration.record(seconds, dimensions)
        if self.span is not None:
            self.span.set_attribute("delivery.outcome", str(outcome))
            if outcome in {
                DeliveryStep.FAILED,
                DeliveryStep.RETRY,
                "cancelled",
                "storage_unavailable",
                "unexpected_error",
            }:
                self.span.set_status(StatusCode.ERROR)
        if outcome == DeliveryStep.IDLE:
            return
        span_context = self.span.get_span_context() if self.span is not None else None
        logging.getLogger("studymate.email").log(
            logging.WARNING if outcome == "storage_unavailable" else logging.INFO,
            LogEvent.WORKER_STEP,
            extra={
                "event": LogEvent.WORKER_STORAGE_UNAVAILABLE
                if outcome == "storage_unavailable"
                else LogEvent.WORKER_STEP,
                "outcome": outcome,
                "duration_seconds": seconds,
                "delivery_id": self.delivery_id,
                "account_id": self.account_id,
                "action_id": self.origin.action_id if self.origin is not None else None,
                "origin_request_id": self.origin.request_id if self.origin is not None else None,
                "origin_trace_id": self.origin.trace_id if self.origin is not None else None,
                "origin_span_id": self.origin.span_id if self.origin is not None else None,
                "trace_id": format(span_context.trace_id, "032x")
                if span_context is not None
                else None,
                "span_id": format(span_context.span_id, "016x")
                if span_context is not None
                else None,
            },
        )

    def close(self) -> None:
        try:
            if self.span is not None:
                self.span.end()
        finally:
            if self.token is not None:
                context.detach(self.token)


_ACTIVE: ContextVar[DeliveryExecution | None] = ContextVar("email_delivery_execution", default=None)


def record_delivery(
    delivery_id: UUID, account_id: UUID, attempt: int, origin: ExecutionOrigin | None
) -> None:
    execution = _ACTIVE.get()
    if execution is not None:
        execution.claimed(delivery_id, account_id, attempt, origin)


class ObservedVerificationDelivery:
    def __init__(
        self,
        step: Callable[[], Awaitable[DeliveryStep]],
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        self.step = step
        self.tracer = tracer
        self.requests = meter.create_counter("worker.email.steps", unit="{step}") if meter else None
        self.duration = (
            meter.create_histogram("worker.email.step.duration", unit="s") if meter else None
        )

    async def __call__(self) -> DeliveryStep:
        execution = DeliveryExecution(self.tracer, self.requests, self.duration)
        token = _ACTIVE.set(execution)
        started = perf_counter()
        outcome: DeliveryOutcome = "unexpected_error"
        try:
            result = await self.step()
            outcome = result
            return result
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except StorageUnavailableError:
            outcome = "storage_unavailable"
            raise
        finally:
            try:
                execution.completed(outcome, max(0, perf_counter() - started))
            finally:
                try:
                    execution.close()
                finally:
                    _ACTIVE.reset(token)
