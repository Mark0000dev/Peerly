"""Cleanup telemetry uses its actual queue kind and retained provenance only."""

from uuid import UUID

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from studymate.application.media.cleanup import TransportCleanupStep
from studymate.infrastructure.observability.media import ObservedMediaStep, record_media_claim
from studymate.infrastructure.observability.origin import ExecutionOrigin


@pytest.mark.parametrize("with_origin", [False, True])
async def test_image_cleanup_span_is_a_root_with_only_actual_origin_link(with_origin: bool) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("synthetic-chat-cleanup")
    origin = ExecutionOrigin(UUID(int=1), UUID(int=2), "1" * 32, "2" * 16) if with_origin else None

    async def step() -> TransportCleanupStep:
        record_media_claim(UUID(int=3), UUID(int=4), UUID(int=5), 1, origin)
        return TransportCleanupStep.CLEANED

    try:
        with tracer.start_as_current_span("unrelated-ambient-request"):
            assert (
                await ObservedMediaStep(step, "chat_cleanup", tracer)()
                == TransportCleanupStep.CLEANED
            )
        span = next(
            item for item in exporter.get_finished_spans() if item.name == "media.chat_cleanup"
        )
        assert span.parent is None
        assert span.attributes is not None
        assert span.attributes["messaging.destination.name"] == "chat_image_transport_cleanup"
        if with_origin:
            assert len(span.links) == 1
            assert span.links[0].context.trace_id == int("1" * 32, 16)
            assert span.attributes["origin.request.id"] == str(UUID(int=1))
        else:
            assert not span.links
            assert "origin.request.id" not in span.attributes
    finally:
        provider.shutdown()
