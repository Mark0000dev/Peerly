"""Actual bootstrap/lifespan, migrated PostgreSQL and real canonical/audit callbacks."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from uuid import UUID, uuid4

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import studymate.bootstrap as bootstrap_module
from studymate.application.errors import StorageUnavailableError
from studymate.config import ObservabilityConfiguration
from studymate.domain.support.cases import SupportReceipt
from studymate.infrastructure.notification_preferences.models import PreferenceRevisionRecord
from studymate.infrastructure.observability.runtime import TelemetryRuntime
from studymate.infrastructure.observability.tracing import OtelHttpTracing
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.product_events import record_support_event
from studymate.infrastructure.support.models import (
    SupportCaseRecord,
    SupportIntentRecord,
    SupportRevisionRecord,
)
from studymate.presentation.identity import IdentityResponse
from studymate.presentation.support.router import SUPPORT_COOKIE
from tests.integration.http_identity import ORIGIN, BrowserHarness, login, verified, write_headers

pytestmark = pytest.mark.integration
PRIVATE_REPLY = "private-support-reply@example.test"
PRIVATE_MESSAGE = "PRIVATE_SUPPORT_MESSAGE_9e71"
PRIVATE_DETAILS = "PRIVATE_SUPPORT_DETAILS_53a2"
SUPPORT_LIMIT = 32768
COMMAND_LIMIT = 8192
EXPECTED_PREFERENCE_CHANGES = 2


@dataclass(slots=True)
class Capture:
    spans: InMemorySpanExporter
    metrics: InMemoryMetricReader
    reject_source: bool = False


@pytest.fixture(autouse=True)
def capture(monkeypatch: pytest.MonkeyPatch) -> Capture:
    exported = InMemorySpanExporter()
    tracer = TracerProvider(shutdown_on_exit=False)
    tracer.add_span_processor(SimpleSpanProcessor(exported))
    metrics = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[metrics], shutdown_on_exit=False)
    runtime = TelemetryRuntime(
        OtelHttpTracing(
            tracer.get_tracer("support-composition"), meter.get_meter("support-composition")
        ),
        tracer,
        meter,
    )
    captured = Capture(exported, metrics)

    def telemetry(
        _configuration: ObservabilityConfiguration | None, _service_name: str = "studymate-api"
    ) -> TelemetryRuntime:
        return runtime

    async def record(session: AsyncSession, actor_id: UUID | None, receipt: SupportReceipt) -> None:
        await record_support_event(session, actor_id, receipt)
        if captured.reject_source:
            raise StorageUnavailableError

    # Both replacements happen before the existing controlled browser fixture builds
    # create_app. The source wrapper calls the real SQL callback before failure.
    monkeypatch.setattr(bootstrap_module, "_telemetry", telemetry)
    monkeypatch.setattr(bootstrap_module, "record_support_event", record)
    return captured


async def public_headers(browser: BrowserHarness) -> dict[str, str]:
    response = await browser.client.post(
        "/api/v1/support-context", json={}, headers={"Origin": ORIGIN}
    )
    assert response.status_code == HTTPStatus.OK
    return {
        "Origin": ORIGIN,
        "X-CSRF-Token": response.json()["csrf_token"],
        "Idempotency-Key": str(uuid4()),
        "X-Action-ID": str(uuid4()),
    }


def support_body() -> dict[str, str]:
    return {
        "topic": "cannot_sign_in",
        "reply_address": PRIVATE_REPLY,
        "message": PRIVATE_MESSAGE,
        "details": PRIVATE_DETAILS,
    }


async def test_anonymous_lost_receipt_recovers_actual_source_without_fake_identity_or_telemetry(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    capture: Capture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="studymate.http")
    headers = await public_headers(browser)
    saved = await browser.client.post("/api/v1/support-cases", json=support_body(), headers=headers)
    assert saved.status_code == HTTPStatus.CREATED
    # Model a discarded response: reload context with only the HttpOnly proof, then
    # retry the retained intent. No account/session/bootstrap call is required.
    reloaded = await public_headers(browser)
    recovered = await browser.client.get("/api/v1/support-cases")
    assert recovered.status_code == HTTPStatus.OK
    assert recovered.json() == {"cases": [saved.json()]}
    assert recovered.headers["cache-control"] == "no-store"
    assert PRIVATE_REPLY not in recovered.text
    assert PRIVATE_MESSAGE not in recovered.text
    reloaded["Idempotency-Key"] = headers["Idempotency-Key"]
    retry = await browser.client.post(
        "/api/v1/support-cases", json=support_body(), headers=reloaded
    )
    assert retry.json() == saved.json()
    case_id = UUID(retry.json()["case_id"])
    async with async_sessionmaker(identity_engine)() as session:
        source = await session.get(SupportCaseRecord, case_id)
        assert source is not None
        assert source.actor_id is None
        assert source.message == PRIVATE_MESSAGE
        assert source.reply_address == PRIVATE_REPLY
        assert source.details == PRIVATE_DETAILS
        assert source.http_request_id == UUID(saved.headers["x-request-id"])
        assert source.action_id == UUID(headers["X-Action-ID"])
        assert source.trace_id is not None
        assert source.span_id is not None
        assert await session.get(SupportRevisionRecord, (case_id, 1)) is not None
        assert await session.scalar(select(func.count()).select_from(SupportIntentRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(AccountRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(ProductEventRecord)) == 0
    token = browser.client.cookies.get(SUPPORT_COOKIE)
    assert token is not None
    snapshots = (caplog.text, repr(capture.metrics.get_metrics_data()))
    for private in (
        PRIVATE_REPLY,
        PRIVATE_MESSAGE,
        PRIVATE_DETAILS,
        token,
        headers["X-CSRF-Token"],
    ):
        assert all(private not in snapshot for snapshot in snapshots)
        for span in capture.spans.get_finished_spans():
            assert private not in repr(span.attributes)
            assert not span.events
    browser.client.cookies.clear()
    assert (
        await browser.client.get(f"/api/v1/support-cases/{case_id}")
    ).status_code == HTTPStatus.NOT_FOUND


async def test_banned_unverified_google_actor_support_remains_owned_and_source_linked(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    await login(browser.client)
    identity = IdentityResponse.model_validate((await browser.client.get("/api/v1/me")).json())
    await public_headers(browser)
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == identity.account_id)
            .values(banned_at=datetime.now(UTC))
        )
    headers = await write_headers(browser.client)
    saved = await browser.client.post(
        "/api/v1/me/support-cases", json=support_body(), headers=headers
    )
    assert saved.status_code == HTTPStatus.CREATED
    case_id = UUID(saved.json()["case_id"])
    assert (await browser.client.get("/api/v1/me/support-cases")).json() == {
        "cases": [saved.json()]
    }
    assert (await browser.client.get(f"/api/v1/me/support-cases/{case_id}")).json() == saved.json()
    async with async_sessionmaker(identity_engine)() as session:
        source = await session.get(SupportCaseRecord, case_id)
        assert source is not None
        assert source.actor_id == identity.account_id
        event = (
            await session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.support_case_id == case_id)
            )
        ).one()
        assert event.kind == "support.received"
        assert event.account_id == identity.account_id
        assert event.support_case_version == 1
        assert event.request_id == UUID(saved.headers["x-request-id"])
    denied = await browser.client.put(
        "/api/v1/me/notification-preference",
        json={"mode": "all_updates", "expected_version": 0},
        headers=headers,
    )
    assert denied.status_code == HTTPStatus.FORBIDDEN
    # Deletion retires ordinary identity authority, but not this narrow proof.
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == identity.account_id)
            .values(deleted_at=datetime.now(UTC))
        )
    assert (
        await browser.client.get(f"/api/v1/me/support-cases/{case_id}")
    ).status_code == HTTPStatus.UNAUTHORIZED
    assert (await browser.client.get(f"/api/v1/support-cases/{case_id}")).json() == saved.json()


async def test_preference_root_callback_has_exact_immutable_revision_and_no_duplicate_event(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owner = await verified(browser, identity_engine)
    path = "/api/v1/me/notification-preference"
    default_headers = await write_headers(browser.client)
    noop = await browser.client.put(
        path, json={"mode": "messages_and_requests", "expected_version": 0}, headers=default_headers
    )
    assert noop.status_code == HTTPStatus.OK
    headers = await write_headers(browser.client)
    body = {"mode": "all_updates", "expected_version": 0}
    changed = await browser.client.put(path, json=body, headers=headers)
    assert changed.status_code == HTTPStatus.OK
    switched = await browser.client.put(
        path,
        json={"mode": "messages_and_requests", "expected_version": 1},
        headers=await write_headers(browser.client),
    )
    assert switched.status_code == HTTPStatus.OK
    assert (await browser.client.put(path, json=body, headers=headers)).json() == changed.json()
    assert (
        await browser.client.put(
            path,
            json={"mode": "messages_and_requests", "expected_version": 0},
            headers=default_headers,
        )
    ).json() == noop.json()
    stale = await browser.client.put(path, json=body, headers=await write_headers(browser.client))
    assert stale.status_code == HTTPStatus.CONFLICT
    assert stale.json()["recovery"]["current_version"] == switched.json()["version"]
    async with async_sessionmaker(identity_engine)() as session:
        events = (
            await session.scalars(
                select(ProductEventRecord).where(
                    ProductEventRecord.kind == "notification_preference.changed"
                )
            )
        ).all()
        assert len(events) == EXPECTED_PREFERENCE_CHANGES
        for event in events:
            assert event.account_id == owner
            source = await session.get(
                PreferenceRevisionRecord, (owner, event.notification_preference_version)
            )
            assert source is not None
            assert source.changed_at == event.occurred_at
            assert event.request_id is not None
            assert event.support_case_id is None


async def test_real_callback_failure_rolls_back_case_intent_and_canonical_source_before_retry(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    capture: Capture,
) -> None:
    await login(browser.client)
    await public_headers(browser)
    headers = await write_headers(browser.client)
    capture.reject_source = True
    rejected = await browser.client.post(
        "/api/v1/me/support-cases", json=support_body(), headers=headers
    )
    assert rejected.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(SupportCaseRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(SupportIntentRecord)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProductEventRecord)
                .where(ProductEventRecord.kind == "support.received")
            )
            == 0
        )
    capture.reject_source = False
    saved = await browser.client.post(
        "/api/v1/me/support-cases", json=support_body(), headers=headers
    )
    assert saved.status_code == HTTPStatus.CREATED
    assert (
        await browser.client.post("/api/v1/me/support-cases", json=support_body(), headers=headers)
    ).json() == saved.json()


async def test_root_support_guard_accepts_bounded_utf8_and_rejects_oversize_before_writes(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    headers = await public_headers(browser)
    body = support_body()
    body["message"] = "字" * 4000
    body["details"] = "字" * 2000
    saved = await browser.client.post("/api/v1/support-cases", json=body, headers=headers)
    assert saved.status_code == HTTPStatus.CREATED
    for method, path, limit in (
        ("POST", "/api/v1/support-cases", SUPPORT_LIMIT),
        ("POST", "/api/v1/me/support-cases", SUPPORT_LIMIT),
        ("POST", "/api/v1/support-context", COMMAND_LIMIT),
        ("PUT", "/api/v1/me/notification-preference", COMMAND_LIMIT),
        ("PUT", f"/api/v1/operator/cases/{uuid4()}/status", COMMAND_LIMIT),
    ):
        oversized = await browser.client.request(
            method, path, content=b"x" * (limit + 1), headers={"Content-Type": "application/json"}
        )
        assert oversized.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert oversized.json()["code"] == "command_body_rejected"
        assert oversized.headers["cache-control"] == "no-store"
        wrong_type = await browser.client.request(
            method, path, content=b"{}", headers={"Content-Type": "text/plain"}
        )
        assert wrong_type.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(SupportCaseRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(SupportIntentRecord)) == 1


async def test_real_root_five_second_body_deadline_rejects_before_source_admission(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    async def stalled_body() -> AsyncIterator[bytes]:
        yield b"{"
        await asyncio.sleep(5.1)
        yield b"}"

    response = await browser.client.post(
        "/api/v1/support-cases",
        content=stalled_body(),
        headers={"Content-Type": "application/json", "Origin": ORIGIN},
    )
    assert response.status_code == HTTPStatus.REQUEST_TIMEOUT
    assert response.json()["code"] == "command_body_rejected"
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(SupportCaseRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(SupportIntentRecord)) == 0


@pytest.mark.parametrize("codepoint", [0xD800, 0xDFFF, 0x7F, 0x85])
@pytest.mark.parametrize("field", ["reply_address", "message", "details"])
async def test_root_rejects_escaped_unicode_controls_without_writes_or_private_echo(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    field: str,
    codepoint: int,
) -> None:
    character = chr(codepoint)
    headers = await public_headers(browser)
    body = support_body()
    body[field] = (
        f"private{character}@example.test" if field == "reply_address" else f"private{character}"
    )
    # Escape deliberately: a lone surrogate is legal escaped input to the JSON
    # decoder and must be rejected before asyncpg attempts UTF-8 encoding.
    response = await browser.client.post(
        "/api/v1/support-cases",
        content=json.dumps(body, ensure_ascii=True).encode("ascii"),
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["code"] == "invalid_fields"
    assert PRIVATE_MESSAGE not in response.text
    assert PRIVATE_REPLY not in response.text
    async with async_sessionmaker(identity_engine)() as session:
        assert await session.scalar(select(func.count()).select_from(SupportCaseRecord)) == 0
        assert await session.scalar(select(func.count()).select_from(SupportIntentRecord)) == 0
