"""Actual SDK in-memory spans; synthetic identifiers, no DB/provider/network."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from studymate.application.errors import StorageUnavailableError
from studymate.domain.student_notifications.delivery import Delivery, Kind, Outcome
from studymate.infrastructure.observability.origin import ExecutionOrigin
from studymate.infrastructure.observability.student_notification_delivery import (
    ObservedStudentNotificationDelivery,
    record_authorized,
    record_completed,
)


@pytest.mark.parametrize("outcome", list(Outcome))
async def test_attempt_has_fresh_consumer_root_link_and_only_technical_attributes(
    outcome: Outcome,
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("notification-test")
    actor, job, event = uuid4(), uuid4(), uuid4()
    origin = ExecutionOrigin(uuid4(), uuid4(), "1" * 32, "2" * 16)

    async def step() -> bool:
        record_authorized(
            Delivery(job, uuid4(), Kind.MESSAGE, datetime.now(UTC)), event, actor, 1, origin
        )
        record_completed(outcome)
        return True

    try:
        with tracer.start_as_current_span("unrelated ambient HTTP"):
            assert await ObservedStudentNotificationDelivery(step, tracer)()
        spans = exporter.get_finished_spans()
        consumer = next(span for span in spans if span.name == "student_notifications.delivery")
        assert consumer.kind == SpanKind.CONSUMER
        assert consumer.parent is None
        assert len(consumer.links) == 1
        assert consumer.links[0].context.trace_id == int("1" * 32, 16)
        assert consumer.links[0].context.span_id == int("2" * 16, 16)
        attributes = consumer.attributes
        assert attributes is not None
        assert attributes["user.id"] == str(actor)
        assert attributes["messaging.message.id"] == str(job)
        assert attributes["product.event.id"] == str(event)
        assert attributes["action.id"] == str(origin.action_id)
        assert attributes["delivery.outcome"] == outcome.value
        assert consumer.events == ()
        assert "body" not in attributes
        assert "endpoint" not in attributes
    finally:
        provider.shutdown()


@pytest.mark.parametrize("failure", ["cancelled", "storage_unavailable", "unexpected_error"])
async def test_failure_propagates_and_execution_context_cannot_leak_to_next_actor(
    failure: str,
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("notification-test")

    async def step() -> bool:
        record_authorized(
            Delivery(uuid4(), uuid4(), Kind.REQUEST, datetime.now(UTC)), uuid4(), None, 1, None
        )
        if failure == "cancelled":
            raise asyncio.CancelledError
        if failure == "storage_unavailable":
            raise StorageUnavailableError
        raise ValueError("SYNTHETIC PRIVATE EXCEPTION TEXT")

    expected = (
        asyncio.CancelledError
        if failure == "cancelled"
        else StorageUnavailableError
        if failure == "storage_unavailable"
        else ValueError
    )
    try:
        with pytest.raises(expected):
            await ObservedStudentNotificationDelivery(step, tracer)()
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes is not None
        assert spans[0].attributes["delivery.outcome"] == failure
        assert "user.id" not in spans[0].attributes
        assert spans[0].links == ()
        assert spans[0].events == ()
        assert not trace.get_current_span().get_span_context().is_valid
        record_authorized(
            Delivery(uuid4(), uuid4(), Kind.REQUEST, datetime.now(UTC)), uuid4(), uuid4(), 1, None
        )
        assert len(exporter.get_finished_spans()) == 1
    finally:
        provider.shutdown()


async def test_idle_step_is_not_a_fake_attempt_or_heartbeat() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    async def idle() -> bool:
        return False

    try:
        assert not await ObservedStudentNotificationDelivery(idle, provider.get_tracer("test"))()
        assert exporter.get_finished_spans() == ()
    finally:
        provider.shutdown()
