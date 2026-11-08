import json
from collections.abc import Iterator
from datetime import timedelta
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import studymate.bootstrap as bootstrap_module
from studymate.application.identity.email_delivery import (
    DeliverVerificationEmail,
    DeliveryStep,
    TransientEmailError,
    VerificationEmail,
)
from studymate.infrastructure.observability.email import ObservedVerificationDelivery
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.persistence.email_delivery import SqlEmailWorkerUnitOfWork
from studymate.infrastructure.persistence.email_models import EmailDeliveryRecord
from studymate.infrastructure.security.email_vault import AeadEmailVault
from tests.integration.http_identity import BrowserHarness, login, write_headers

pytestmark = pytest.mark.integration
PRIVATE = "private-student-email-provider-error"


class Telemetry:
    def __init__(self) -> None:
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider(shutdown_on_exit=False)
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))


@pytest.fixture(autouse=True)
def telemetry(monkeypatch: pytest.MonkeyPatch) -> Iterator[Telemetry]:
    controlled = Telemetry()

    def tracing() -> OtelHttpTracing:
        return OtelHttpTracing(controlled.provider.get_tracer("synthetic-api"))

    monkeypatch.setattr(bootstrap_module, "OtelHttpTracing", tracing)
    try:
        yield controlled
    finally:
        controlled.provider.shutdown()


class Sender:
    def __init__(self) -> None:
        self.unavailable = False

    async def send(self, message: VerificationEmail, delivery_id: UUID) -> None:
        assert message.code.value
        assert delivery_id.int > 0
        if self.unavailable:
            raise TransientEmailError(PRIVATE)


async def start(browser: BrowserHarness, action_id: UUID) -> tuple[UUID, UUID]:
    await login(browser.client)
    headers = await write_headers(browser.client)
    headers["X-Action-ID"] = str(action_id)
    headers["traceparent"] = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    created = await browser.client.post(
        "/api/v1/auth/email-challenges", json={"email": "tp@mail.apu.edu.my"}, headers=headers
    )
    assert created.status_code == HTTPStatus.ACCEPTED
    return UUID(created.json()["id"]), UUID(created.headers["x-request-id"])


async def test_retry_uses_new_consumer_traces_linked_to_retained_initiating_context(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    telemetry: Telemetry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.email")
    action_id = uuid4()
    challenge_id, request_id = await start(browser, action_id)
    sender = Sender()
    step = DeliverVerificationEmail(
        SqlEmailWorkerUnitOfWork(async_sessionmaker(identity_engine)),
        sender,
        AeadEmailVault(bytes.fromhex("03" * 32), bytes.fromhex("01" * 32)),
    )
    worker = ObservedVerificationDelivery(step, telemetry.provider.get_tracer("synthetic-worker"))
    sender.unavailable = True
    assert await worker() == DeliveryStep.RETRY
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(EmailDeliveryRecord).values(due_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    sender.unavailable = False
    assert await worker() == DeliveryStep.DELIVERED
    spans = telemetry.exporter.get_finished_spans()
    matching = [span for span in spans if span.name == "POST /api/v1/auth/email-challenges"]
    assert len(matching) == 1, [span.name for span in spans]
    initiating = matching[0]
    attempts = [span for span in spans if span.name == "email.delivery"]
    assert len({span.context.trace_id for span in attempts if span.context is not None}) == len(
        attempts
    )
    assert len(attempts) > 1
    assert initiating.context is not None
    for span in attempts:
        assert span.parent is None
        assert len(span.links) == 1
        assert span.links[0].context.trace_id == initiating.context.trace_id
        assert span.links[0].context.span_id == initiating.context.span_id
        assert span.attributes is not None
        assert span.attributes["origin.request.id"] == str(request_id)
        assert span.attributes["action.id"] == str(action_id)
        assert not span.events
        assert PRIVATE not in span.to_json()
    async with async_sessionmaker(identity_engine)() as session:
        stored = (
            await session.scalars(
                select(EmailDeliveryRecord).where(EmailDeliveryRecord.challenge_id == challenge_id)
            )
        ).one()
        assert stored.sealed_envelope is None
        assert stored.origin_request_id == request_id
        assert stored.origin_action_id == action_id
        assert stored.origin_trace_id == format(initiating.context.trace_id, "032x")
        assert stored.origin_span_id == format(initiating.context.span_id, "016x")
    logs = [
        SafeJsonFormatter().format(record)
        for record in caplog.records
        if record.name == "studymate.email"
    ]
    assert all(PRIVATE not in line and "tp@mail.apu.edu.my" not in line for line in logs)
    assert {json.loads(line)["outcome"] for line in logs} == {"retry", "delivered"}
    assert all(json.loads(line)["origin_request_id"] == str(request_id) for line in logs)


@pytest.mark.parametrize("invalid", ["orphan_request", "missing_span", "zero_trace"])
async def test_database_rejects_partial_or_invalid_delivery_origin(
    browser: BrowserHarness, identity_engine: AsyncEngine, invalid: str
) -> None:
    await start(browser, uuid4())
    if invalid == "orphan_request":
        statement = update(EmailDeliveryRecord).values(origin_request_id=None)
    elif invalid == "missing_span":
        statement = update(EmailDeliveryRecord).values(origin_span_id=None)
    else:
        statement = update(EmailDeliveryRecord).values(origin_trace_id="0" * 32)
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(statement)
