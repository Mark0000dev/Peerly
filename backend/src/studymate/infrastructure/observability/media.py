"""Bounded media-worker signals; no image bytes, signed access or failure text."""

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

from studymate.application.chat_images.worker import ChatImageProcessingStep
from studymate.application.errors import StorageUnavailableError
from studymate.application.media.cleanup import TransportCleanupStep
from studymate.application.media.worker import PhotoProcessingStep
from studymate.infrastructure.observability.logging import LogEvent
from studymate.infrastructure.observability.origin import ExecutionOrigin

MediaKind = Literal["photo", "chat_image", "cleanup", "chat_cleanup"]


@dataclass(slots=True)
class MediaExecution:
    kind: MediaKind
    tracer: Tracer | None
    steps: Counter | None
    duration: Histogram | None
    span: Span | None = None
    token: Token[Context] | None = None
    upload_id: UUID | None = None
    account_id: UUID | None = None
    attempt_id: UUID | None = None
    origin: ExecutionOrigin | None = None

    def claimed(
        self,
        upload_id: UUID,
        account_id: UUID,
        attempt_id: UUID,
        attempt: int,
        origin: ExecutionOrigin | None,
    ) -> None:
        self.upload_id, self.account_id = upload_id, account_id
        self.attempt_id, self.origin = attempt_id, origin
        if self.tracer is None:
            return
        attributes: dict[str, str | int] = {
            "messaging.system": "postgresql",
            "messaging.destination.name": {
                "photo": "photo_uploads",
                "chat_image": "chat_image_preparations",
                "cleanup": "photo_transport_cleanup",
                "chat_cleanup": "chat_image_transport_cleanup",
            }[self.kind],
            "media.upload.id": str(upload_id),
            "media.attempt.id": str(attempt_id),
            "media.attempt.number": attempt,
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
            f"media.{self.kind}",
            context=Context(),
            kind=SpanKind.CONSUMER,
            attributes=attributes,
            links=links,
        )
        self.token = context.attach(trace.set_span_in_context(self.span, Context()))

    def completed(self, outcome: str, seconds: float) -> None:
        # Only the controlled enum results or fixed wrapper outcomes reach here.
        dimensions = {"worker": self.kind, "outcome": outcome}
        if self.steps is not None:
            self.steps.add(1, dimensions)
        if self.duration is not None:
            self.duration.record(seconds, dimensions)
        if self.span is not None:
            self.span.set_attribute("media.outcome", outcome)
            if outcome in {
                "retry",
                "rejected",
                "cancelled",
                "storage_unavailable",
                "unexpected_error",
            }:
                self.span.set_status(StatusCode.ERROR)
        if outcome == "idle":
            return
        span_context = self.span.get_span_context() if self.span is not None else None
        logging.getLogger("studymate.media").log(
            logging.WARNING if outcome == "storage_unavailable" else logging.INFO,
            LogEvent.WORKER_STEP,
            extra={
                "event": LogEvent.WORKER_STORAGE_UNAVAILABLE
                if outcome == "storage_unavailable"
                else LogEvent.WORKER_STEP,
                "worker": self.kind,
                "outcome": outcome,
                "duration_seconds": seconds,
                "upload_id": self.upload_id,
                "account_id": self.account_id,
                "attempt_id": self.attempt_id,
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


_ACTIVE: ContextVar[MediaExecution | None] = ContextVar("media_execution", default=None)


def record_media_claim(
    upload_id: UUID,
    account_id: UUID,
    attempt_id: UUID,
    attempt: int,
    origin: ExecutionOrigin | None,
) -> None:
    execution = _ACTIVE.get()
    if execution is not None:
        execution.claimed(upload_id, account_id, attempt_id, attempt, origin)


class ObservedMediaStep[
    MediaStep: (PhotoProcessingStep, ChatImageProcessingStep, TransportCleanupStep)
]:
    def __init__(
        self,
        step: Callable[[], Awaitable[MediaStep]],
        kind: MediaKind,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
    ) -> None:
        self.step: Callable[[], Awaitable[MediaStep]] = step
        self.kind = kind
        self.tracer = tracer
        self.steps = meter.create_counter("worker.media.steps", unit="{step}") if meter else None
        self.duration = (
            meter.create_histogram("worker.media.step.duration", unit="s") if meter else None
        )

    async def __call__(self) -> MediaStep:
        execution = MediaExecution(self.kind, self.tracer, self.steps, self.duration)
        token = _ACTIVE.set(execution)
        started = perf_counter()
        outcome = "unexpected_error"
        try:
            result = await self.step()
            outcome = result.value
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
