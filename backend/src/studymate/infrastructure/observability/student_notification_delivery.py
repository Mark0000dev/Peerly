"""Link a real notification attempt to retained source origin; no payload/metric labels."""

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from opentelemetry import context, trace
from opentelemetry.context import Context
from opentelemetry.trace import Link, Span, SpanContext, SpanKind, StatusCode, TraceFlags, Tracer

from studymate.application.errors import StorageUnavailableError
from studymate.domain.student_notifications.delivery import Delivery, Outcome
from studymate.infrastructure.observability.origin import ExecutionOrigin


@dataclass(slots=True)
class _Execution:
    tracer: Tracer
    span: Span | None = None
    token: Token[Context] | None = None
    outcome: str = Outcome.UNKNOWN.value

    def authorized(
        self,
        delivery: Delivery,
        event_id: UUID,
        actor_id: UUID | None,
        attempt: int,
        origin: ExecutionOrigin | None,
    ) -> None:
        if self.span is not None:
            raise RuntimeError("One authorization per notification step required")
        attributes: dict[str, str | int] = {
            "messaging.system": "postgresql",
            "messaging.destination.name": "student_notifications",
            "messaging.message.id": str(delivery.id),
            "product.event.id": str(event_id),
            "notification.kind": delivery.kind.value,
            "delivery.attempt": attempt,
        }
        if actor_id is not None:
            attributes["user.id"] = str(actor_id)
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
            "student_notifications.delivery",
            context=Context(),
            kind=SpanKind.CONSUMER,
            attributes=attributes,
            links=links,
        )
        self.token = context.attach(trace.set_span_in_context(self.span, Context()))

    def close(self) -> None:
        try:
            if self.span is not None:
                self.span.set_attribute("delivery.outcome", self.outcome)
                if self.outcome in {"cancelled", "storage_unavailable", "unexpected_error"}:
                    self.span.set_status(StatusCode.ERROR)
                self.span.end()
        finally:
            if self.token is not None:
                context.detach(self.token)


_ACTIVE: ContextVar[_Execution | None] = ContextVar("student_notification_execution", default=None)


def record_authorized(
    delivery: Delivery,
    event_id: UUID,
    actor_id: UUID | None,
    attempt: int,
    origin: ExecutionOrigin | None,
) -> None:
    execution = _ACTIVE.get()
    if execution is not None:
        execution.authorized(delivery, event_id, actor_id, attempt, origin)


def record_completed(outcome: Outcome) -> None:
    execution = _ACTIVE.get()
    if execution is not None:
        execution.outcome = outcome.value


@dataclass(frozen=True, slots=True)
class ObservedStudentNotificationDelivery:
    step: Callable[[], Awaitable[bool]]
    tracer: Tracer

    async def __call__(self) -> bool:
        execution = _Execution(self.tracer)
        token = _ACTIVE.set(execution)
        failure: Literal["cancelled", "storage_unavailable", "unexpected_error"] | None = (
            "unexpected_error"
        )
        try:
            result = await self.step()
            failure = None
            return result
        except asyncio.CancelledError:
            failure = "cancelled"
            raise
        except StorageUnavailableError:
            failure = "storage_unavailable"
            raise
        finally:
            if failure is not None:
                execution.outcome = failure
            try:
                execution.close()
            finally:
                _ACTIVE.reset(token)
