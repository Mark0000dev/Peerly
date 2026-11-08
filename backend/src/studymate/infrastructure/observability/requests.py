"""Fixed-dimension maintenance signals; request bodies and failure text never enter telemetry."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter, time_ns

from opentelemetry.context import Context
from opentelemetry.metrics import Meter
from opentelemetry.trace import SpanKind, StatusCode, Tracer

from studymate.application.errors import StorageUnavailableError
from studymate.application.requests.expiry import MAX_EXPIRY_BATCH
from studymate.domain.requests.states import ConnectionRequest
from studymate.infrastructure.observability.logging import LogEvent


class ObservedRequestExpiry:
    def __init__(
        self,
        step: Callable[[], Awaitable[tuple[ConnectionRequest, ...]]],
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        self.step = step
        self.tracer = tracer
        self.steps = (
            meter.create_counter("worker.requests.expiry.steps", unit="{step}") if meter else None
        )
        self.finalized = (
            meter.create_counter("worker.requests.finalized", unit="{request}") if meter else None
        )
        self.duration = (
            meter.create_histogram("worker.requests.expiry.duration", unit="s") if meter else None
        )

    async def __call__(self) -> tuple[ConnectionRequest, ...]:
        started, started_ns = perf_counter(), time_ns()
        changed: tuple[ConnectionRequest, ...] = ()
        outcome = "unexpected_error"
        try:
            changed = await self.step()
            if len(changed) > MAX_EXPIRY_BATCH:
                raise RuntimeError("Observed expiry source exceeded its bounded batch")
            outcome = "changed" if changed else "idle"
            return changed
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except StorageUnavailableError:
            outcome = "storage_unavailable"
            raise
        finally:
            seconds = max(0, perf_counter() - started)
            dimensions = {"outcome": outcome}
            if self.steps is not None:
                self.steps.add(1, dimensions)
            if self.duration is not None:
                self.duration.record(seconds, dimensions)
            if self.finalized is not None and outcome == "changed":
                for request in changed:
                    self.finalized.add(1, {"state": request.state.value})
            # Start only for actual work/error, using the measured operation's
            # real start time. Idle polling invents neither spans nor human work.
            if outcome != "idle":
                self.completed(changed, outcome, started_ns, seconds)

    def completed(
        self, changed: tuple[ConnectionRequest, ...], outcome: str, started_ns: int, seconds: float
    ) -> None:
        span = (
            self.tracer.start_span(
                "requests.expiry", context=Context(), kind=SpanKind.CONSUMER, start_time=started_ns
            )
            if self.tracer is not None
            else None
        )
        try:
            if span is not None:
                span.set_attribute("messaging.system", "postgresql")
                span.set_attribute("messaging.destination.name", "connection_requests")
                span.set_attribute("request.expiry.outcome", outcome)
                if outcome == "changed":
                    span.set_attribute(
                        "connection.request.ids", tuple(str(request.id) for request in changed)
                    )
                else:
                    span.set_status(StatusCode.ERROR)
            context = span.get_span_context() if span is not None else None
            logging.getLogger("studymate.requests").log(
                logging.WARNING if outcome == "storage_unavailable" else logging.INFO,
                LogEvent.WORKER_STEP,
                extra={
                    "event": LogEvent.WORKER_STORAGE_UNAVAILABLE
                    if outcome == "storage_unavailable"
                    else LogEvent.WORKER_STEP,
                    "worker": "request_expiry",
                    "outcome": outcome,
                    "duration_seconds": seconds,
                    "trace_id": format(context.trace_id, "032x") if context is not None else None,
                    "span_id": format(context.span_id, "016x") if context is not None else None,
                },
            )
        finally:
            if span is not None:
                span.end()
