"""Canonical root HTTP/lifespan -> real migrated PG -> linked worker attempt; source only."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate import bootstrap
from studymate.application.student_notifications.worker import DeliverNextStudentNotification
from studymate.config import ObservabilityConfiguration
from studymate.domain.student_notifications.delivery import Delivery, Outcome, State
from studymate.infrastructure.observability.runtime import TelemetryRuntime
from studymate.infrastructure.observability.student_notification_delivery import (
    ObservedStudentNotificationDelivery,
)
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.student_notifications.models import DeliveryRecord
from studymate.infrastructure.student_notifications.queue import SqlStudentNotifications, clock
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.requests.fixture import prepared, sent
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class SourceRuntime:
    api_spans: InMemorySpanExporter
    worker_spans: InMemorySpanExporter
    worker_provider: TracerProvider
    captures_origin: bool


@pytest.fixture(autouse=True)
def source_runtime(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SourceRuntime]:
    value: object = getattr(request, "param", True)
    if not isinstance(value, bool):
        raise TypeError("Expected controlled source-tracing switch")
    api_exporter, worker_exporter = InMemorySpanExporter(), InMemorySpanExporter()
    api = TracerProvider(resource=Resource({"service.name": "studymate-api"}))
    worker = TracerProvider(
        resource=Resource({"service.name": "peerly-student-notifications-worker"})
    )
    api.add_span_processor(SimpleSpanProcessor(api_exporter))
    worker.add_span_processor(SimpleSpanProcessor(worker_exporter))
    meter = MeterProvider()
    runtime = TelemetryRuntime(
        OtelHttpTracing(api.get_tracer("actual-http"), meter.get_meter("actual-http")), api, meter
    )

    def telemetry(
        configuration: ObservabilityConfiguration | None, service_name: str = "studymate-api"
    ) -> TelemetryRuntime | None:
        assert configuration is None
        assert service_name == "studymate-api"
        return runtime if value else None

    monkeypatch.setattr(bootstrap, "_telemetry", telemetry)
    try:
        yield SourceRuntime(api_exporter, worker_exporter, worker, value)
    finally:
        worker.shutdown()
        if not value:
            # With source instrumentation disabled the canonical API owns no SDK.
            meter.shutdown()
            api.shutdown()


class Accepted:
    async def send(self, delivery: Delivery) -> Outcome:
        assert delivery.id is not None
        return Outcome.ACCEPTED


async def inspect_join(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[DeliveryRecord, ProductEventRecord]:
    async with sessions() as session:
        rows = (
            await session.execute(
                select(DeliveryRecord, ProductEventRecord).join(
                    ProductEventRecord, ProductEventRecord.id == DeliveryRecord.event_id
                )
            )
        ).all()
        assert len(rows) == 1
        job, event = rows[0]
        return job, event


def assert_span(
    runtime: SourceRuntime,
    job: DeliveryRecord,
    event: ProductEventRecord,
    actor: UUID,
    outcome: str,
) -> None:
    spans = runtime.worker_spans.get_finished_spans()
    consumers = [span for span in spans if span.name == "student_notifications.delivery"]
    assert len(consumers) == 1
    span = consumers[0]
    assert span.parent is None
    attributes = span.attributes
    assert attributes is not None
    assert attributes["messaging.message.id"] == str(job.id)
    assert attributes["product.event.id"] == str(event.id)
    assert attributes["user.id"] == str(actor)
    assert attributes["delivery.outcome"] == outcome
    assert span.events == ()
    if runtime.captures_origin:
        assert event.trace_id is not None
        assert event.span_id is not None
        assert event.request_id is not None
        assert event.action_id is not None
        assert len(span.links) == 1
        assert span.links[0].context.trace_id == int(event.trace_id, 16)
        assert span.links[0].context.span_id == int(event.span_id, 16)
        originals = [
            s
            for s in runtime.api_spans.get_finished_spans()
            if s.context is not None
            and s.context.trace_id == int(event.trace_id, 16)
            and s.context.span_id == int(event.span_id, 16)
        ]
        assert len(originals) == 1
        assert originals[0].attributes is not None
        assert originals[0].attributes["user.id"] == str(actor)
        assert attributes["origin.request.id"] == str(event.request_id)
        assert attributes["action.id"] == str(event.action_id)
    else:
        # SDK absence does not disable canonical server HTTP correlation.
        assert event.request_id is not None
        assert event.action_id is not None
        assert event.trace_id is None
        assert event.span_id is None
        assert span.links == ()
        assert attributes["origin.request.id"] == str(event.request_id)
        assert attributes["action.id"] == str(event.action_id)
    for forbidden in ["body", "text", "note", "endpoint", "token", "recipient.email"]:
        assert forbidden not in attributes


@pytest.mark.parametrize("source_runtime", [True, False], indirect=True)
async def test_actual_message_http_commit_to_worker_link_and_honest_missing_origin(
    source_runtime: SourceRuntime, browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    thread = await chat(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    queue = SqlStudentNotifications(sessions)
    await queue.activate()
    browser.client.cookies.set(SESSION_COOKIE, thread.sender.credential.value)
    action_id, client_id = uuid4(), uuid4()
    headers = {**await write_headers(browser.client), "X-Action-Id": str(action_id)}
    path = f"/api/v1/conversations/{thread.conversation_id}/messages"
    body = {"client_message_id": str(client_id), "text": "SYNTHETIC PRIVATE MESSAGE NEVER EXPORTED"}
    response = await browser.client.post(path, json=body, headers=headers)
    assert response.status_code == HTTPStatus.OK
    assert (await browser.client.post(path, json=body, headers=headers)).json() == response.json()
    assert await queue.materialize() == 1
    step = ObservedStudentNotificationDelivery(
        DeliverNextStudentNotification(queue, Accepted()),
        source_runtime.worker_provider.get_tracer("real-worker"),
    )
    assert await step()
    assert not await step()  # Durable completed job is not replayed; no fake idle span.
    job, event = await inspect_join(sessions)
    assert job.state == State.DELIVERED.value
    assert job.actor_id == thread.sender.id
    assert event.account_id == thread.sender.id
    assert job.recipient_id == thread.recipient.id
    assert event.action_id == action_id
    assert str(event.request_id) == response.headers["x-request-id"]
    assert_span(source_runtime, job, event, thread.sender.id, Outcome.ACCEPTED.value)


@pytest.mark.parametrize("accepted", [False, True])
async def test_actual_request_http_origin_uses_initiator_not_stable_sender(
    source_runtime: SourceRuntime,
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    accepted: bool,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    initial = await sent(api, sender, recipient) if accepted else None
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    queue = SqlStudentNotifications(sessions)
    await queue.activate()
    acting = recipient if accepted else sender
    browser.client.cookies.set(SESSION_COOKIE, acting.credential.value)
    action_id = uuid4()
    if accepted:
        assert initial is not None
        path = f"/api/v1/requests/{initial.id}/accept"
        body: dict[str, object] = {"person_id": str(sender.id), "expected_version": initial.version}
    else:
        preview = await browser.client.post(
            "/api/v1/requests/preview",
            json={"person_id": str(recipient.id), "mode": "find_help"},
            headers=await write_headers(browser.client),
        )
        assert preview.status_code == HTTPStatus.OK
        path = "/api/v1/requests"
        body = {
            "person_id": str(recipient.id),
            "preview_id": preview.json()["preview_id"],
            "text": "SYNTHETIC PRIVATE REQUEST",
            "note": "SYNTHETIC PRIVATE NOTE",
        }
    response = await browser.client.post(
        path,
        json=body,
        headers={**await write_headers(browser.client), "X-Action-Id": str(action_id)},
    )
    assert response.status_code == HTTPStatus.OK
    assert await queue.materialize() == 1
    assert await ObservedStudentNotificationDelivery(
        DeliverNextStudentNotification(queue, Accepted()),
        source_runtime.worker_provider.get_tracer("real-worker"),
    )()
    job, event = await inspect_join(sessions)
    assert event.account_id == sender.id
    assert event.request_initiator_id == acting.id
    assert job.actor_id == acting.id
    if accepted:
        assert acting.id != sender.id
        assert job.recipient_id == sender.id
    assert event.action_id == action_id
    assert str(event.request_id) == response.headers["x-request-id"]
    assert_span(source_runtime, job, event, acting.id, Outcome.ACCEPTED.value)


async def test_actual_http_job_lost_lease_stays_unknown_in_span_and_durable_queue(
    source_runtime: SourceRuntime, browser: BrowserHarness, identity_engine: AsyncEngine
) -> None:
    thread = await chat(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    queue = SqlStudentNotifications(sessions)
    await queue.activate()
    browser.client.cookies.set(SESSION_COOKIE, thread.sender.credential.value)
    response = await browser.client.post(
        f"/api/v1/conversations/{thread.conversation_id}/messages",
        json={"client_message_id": str(uuid4()), "text": "SYNTHETIC PRIVATE FENCED MESSAGE"},
        headers={**await write_headers(browser.client), "X-Action-Id": str(uuid4())},
    )
    assert response.status_code == HTTPStatus.OK
    assert await queue.materialize() == 1

    class LostLease:
        async def send(self, delivery: Delivery) -> Outcome:
            async with sessions.begin() as session:
                await session.execute(
                    update(DeliveryRecord)
                    .where(DeliveryRecord.id == delivery.id)
                    .values(lease_until=await clock(session) - timedelta(seconds=1))
                )
            return Outcome.ACCEPTED

    assert await ObservedStudentNotificationDelivery(
        DeliverNextStudentNotification(queue, LostLease()),
        source_runtime.worker_provider.get_tracer("real-worker"),
    )()
    assert await queue.claim() is None  # Existing expiry sweep fences sending to UNKNOWN.
    job, event = await inspect_join(sessions)
    assert job.state == State.UNKNOWN.value
    assert_span(source_runtime, job, event, thread.sender.id, Outcome.UNKNOWN.value)
