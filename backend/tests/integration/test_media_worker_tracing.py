import asyncio
import hashlib
import json
from collections.abc import Iterator
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import studymate.bootstrap as bootstrap_module
from studymate.application.media.cleanup import TransportCleanupStep
from studymate.application.media.worker import PhotoProcessingStep
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.infrastructure.observability.media import ObservedMediaStep
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.persistence.media_origin_models import MediaOriginRecord
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from tests.image_fixture import encoded
from tests.integration.http_identity import BrowserHarness, verified, write_headers
from tests.integration.media_fixture import worker
from tests.integration.test_transport_cleanup import age_transport, cleaner

pytestmark = pytest.mark.integration


@pytest.fixture
def tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TracerProvider, InMemorySpanExporter]]:
    exported = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exported))

    def http_tracing() -> OtelHttpTracing:
        return OtelHttpTracing(provider.get_tracer("synthetic-api"))

    monkeypatch.setattr(bootstrap_module, "OtelHttpTracing", http_tracing)
    try:
        yield provider, exported
    finally:
        provider.shutdown()


async def queued_http(
    browser: BrowserHarness, engine: AsyncEngine, action: UUID
) -> tuple[UUID, UUID]:
    await verified(browser, engine)
    data = encoded()
    headers = await write_headers(browser.client)
    headers["X-Action-ID"] = str(uuid4())
    created = await browser.client.post(
        "/api/v1/media/uploads",
        json={
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "content_type": "image/png",
            "expected_photo_version": 0,
        },
        headers=headers,
    )
    assert created.status_code == HTTPStatus.ACCEPTED
    upload_id = UUID(created.json()["id"])
    browser.storage.data = data
    headers = await write_headers(browser.client)
    headers["X-Action-ID"] = str(action)
    headers["traceparent"] = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    finalized = await browser.client.post(
        f"/api/v1/media/uploads/{upload_id}/finalize", headers=headers
    )
    assert finalized.status_code == HTTPStatus.ACCEPTED
    assert (
        await browser.client.post(f"/api/v1/media/uploads/{upload_id}/finalize", headers=headers)
    ).json() == finalized.json()
    return upload_id, UUID(finalized.headers["x-request-id"])


async def test_photo_retries_link_finalize_origin_without_private_content(
    tracing: tuple[TracerProvider, InMemorySpanExporter],
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider, exported = tracing
    caplog.set_level("INFO", logger="studymate.media")
    action = uuid4()
    upload_id, request_id = await queued_http(browser, identity_engine, action)
    processor = BoundedImageProcessor()
    step = ObservedMediaStep(
        worker(identity_engine, browser.storage, processor),
        "photo",
        provider.get_tracer("synthetic-worker"),
    )
    try:
        browser.storage.unavailable = True
        assert await step() == PhotoProcessingStep.RETRY
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(PhotoAttemptRecord).values(next_attempt_at=func.clock_timestamp())
            )
        browser.storage.unavailable = False
        assert await step() == PhotoProcessingStep.READY
    finally:
        await processor.close()
    attempts = [span for span in exported.get_finished_spans() if span.name == "media.photo"]
    assert len(attempts) == 1 + 1
    assert attempts[0].context is not None
    assert attempts[1].context is not None
    assert attempts[0].context.trace_id != attempts[1].context.trace_id
    for span in attempts:
        assert span.parent is None
        assert len(span.links) == 1
        assert span.links[0].context.trace_id == int("a" * 32, 16)
        assert span.attributes is not None
        assert span.attributes["origin.request.id"] == str(request_id)
        assert span.attributes["action.id"] == str(action)
        assert not span.events
    async with async_sessionmaker(identity_engine)() as session:
        rows = (
            await session.scalars(
                select(MediaOriginRecord).where(MediaOriginRecord.upload_id == upload_id)
            )
        ).all()
        assert {row.phase for row in rows} == {"created", "queued"}
        queued = next(row for row in rows if row.phase == "queued")
        assert queued.request_id == request_id
        assert queued.action_id == action
        assert queued.trace_id == "a" * 32
    logs = [
        json.loads(SafeJsonFormatter().format(record))
        for record in caplog.records
        if record.name == "studymate.media"
    ]
    assert {record["outcome"] for record in logs} == {"retry", "ready"}
    assert all(record["upload_id"] == str(upload_id) for record in logs)
    assert all(record["origin_request_id"] == str(request_id) for record in logs)
    assert "signed" not in json.dumps(logs)


async def test_transport_cleanup_keeps_retained_execution_origin_after_processing(
    tracing: tuple[TracerProvider, InMemorySpanExporter],
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    provider, exported = tracing
    action = uuid4()
    upload_id, request_id = await queued_http(browser, identity_engine, action)
    processor = BoundedImageProcessor()
    try:
        assert (
            await worker(identity_engine, browser.storage, processor)() == PhotoProcessingStep.READY
        )
    finally:
        await processor.close()
    retained = browser.storage.retained.copy()
    await age_transport(identity_engine)
    step = ObservedMediaStep(
        cleaner(identity_engine, browser.storage),
        "cleanup",
        provider.get_tracer("synthetic-worker"),
    )
    assert await step() == TransportCleanupStep.CLEANED
    assert await step() == TransportCleanupStep.IDLE
    spans = [span for span in exported.get_finished_spans() if span.name == "media.cleanup"]
    assert len(spans) == 1
    assert spans[0].parent is None
    assert len(spans[0].links) == 1
    assert spans[0].attributes is not None
    assert spans[0].attributes["origin.request.id"] == str(request_id)
    assert spans[0].attributes["media.upload.id"] == str(upload_id)
    assert spans[0].attributes["action.id"] == str(action)
    assert browser.storage.retained == retained


async def test_slow_storage_processing_does_not_hold_status_lock_or_api_readiness(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    upload_id, _ = await queued_http(browser, identity_engine, uuid4())
    browser.storage.pause = True
    processor = BoundedImageProcessor()
    task = asyncio.create_task(worker(identity_engine, browser.storage, processor)())
    try:
        await asyncio.wait_for(browser.storage.started.wait(), timeout=2)
        async with asyncio.timeout(2):
            status = await browser.client.get(f"/api/v1/media/{upload_id}")
            profile = await browser.client.get("/api/v1/me/profile")
            readiness = await browser.client.get("/api/ready")
        assert status.status_code == HTTPStatus.OK
        assert status.json()["state"] == "processing"
        assert profile.status_code == HTTPStatus.OK
        assert readiness.status_code == HTTPStatus.OK
    finally:
        browser.storage.release.set()
        try:
            assert await task == PhotoProcessingStep.READY
        finally:
            await processor.close()
