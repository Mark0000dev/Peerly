"""Fixed-cardinality transport maintenance signals, without canonical/private payloads."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter, time_ns

from opentelemetry.context import Context
from opentelemetry.metrics import Meter
from opentelemetry.trace import SpanKind, StatusCode, Tracer

from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.changes.loop import ChangeMaintenance
from studymate.infrastructure.observability.logging import LogEvent


class ObservedChangeStep:
    def __init__(
        self,
        step: Callable[[], Awaitable[int]],
        kind: ChangeMaintenance,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        self.step = step
        self.kind = kind
        self.tracer = tracer
        self.steps = meter.create_counter("worker.changes.steps", unit="{step}") if meter else None
        self.changed = (
            meter.create_counter("worker.changes.hints", unit="{hint}") if meter else None
        )
        self.duration = (
            meter.create_histogram("worker.changes.duration", unit="s") if meter else None
        )

    async def __call__(self) -> int:
        started, started_ns = perf_counter(), time_ns()
        outcome = "unexpected_error"
        changed = 0
        try:
            changed = await self.step()
            if isinstance(changed, bool) or changed < 0:
                raise RuntimeError("Observed transport maintenance requires nonnegative counts")
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
            dimensions = {"maintenance": self.kind.value, "outcome": outcome}
            if self.steps is not None:
                self.steps.add(1, dimensions)
            if self.duration is not None:
                self.duration.record(seconds, dimensions)
            if self.changed is not None and outcome == "changed":
                self.changed.add(changed, {"maintenance": self.kind.value})
            if outcome != "idle":
                self.completed(outcome, started_ns, seconds)

    def completed(self, outcome: str, started_ns: int, seconds: float) -> None:
        span = (
            self.tracer.start_span(
                f"changes.{self.kind.value}",
                context=Context(),
                kind=SpanKind.CONSUMER,
                start_time=started_ns,
            )
            if self.tracer is not None
            else None
        )
        try:
            if span is not None:
                span.set_attribute("messaging.system", "postgresql")
                span.set_attribute("change.maintenance", self.kind.value)
                span.set_attribute("change.outcome", outcome)
                if outcome != "changed":
                    span.set_status(StatusCode.ERROR)
            context = span.get_span_context() if span is not None else None
            event = (
                LogEvent.WORKER_STORAGE_UNAVAILABLE
                if outcome == "storage_unavailable"
                else LogEvent.WORKER_STEP
            )
            logging.getLogger("studymate.changes").log(
                logging.WARNING if outcome == "storage_unavailable" else logging.INFO,
                event,
                extra={
                    "event": event,
                    "worker": f"change_{self.kind.value}",
                    "outcome": outcome,
                    "duration_seconds": seconds,
                    "trace_id": format(context.trace_id, "032x") if context is not None else None,
                    "span_id": format(context.span_id, "016x") if context is not None else None,
                },
            )
        finally:
            if span is not None:
                span.end()
