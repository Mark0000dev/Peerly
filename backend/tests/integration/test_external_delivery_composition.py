"""Actual root intake/inspection and worker composition, with controlled provider transport."""

import asyncio
import ssl
from datetime import datetime
from http import HTTPStatus
from uuid import uuid4

import httpx2
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import QueuePool

from studymate import bootstrap
from studymate.config import ExternalDeliveryWorkerSettings, UmamiDeliveryConfiguration
from studymate.infrastructure.client_observations.models import ClientObservationRecord
from studymate.infrastructure.external_delivery.models import (
    DeliveryDestinationRecord,
    DeliverySourceRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.browser import SESSION_COOKIE
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.operator.test_reads import operator
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration
INTAKE = "/api/v1/telemetry/events"


async def test_root_unverified_actor_intake_is_deduped_and_operator_source_is_audited(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
) -> None:
    owner = await actor(identity_engine, verified=False)
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, owner.credential.value)
    headers = await write_headers(browser.client)
    event_id = uuid4()
    async with async_sessionmaker(identity_engine)() as session:
        now = await session.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    payload = {
        "schema_version": 1,
        "expected_actor_id": str(owner.id),
        "events": [
            {
                "kind": "quality.observed",
                "event_id": str(event_id),
                "observed_at": now.isoformat(),
                "screen": "verification",
                "reason": "exhausted",
                "count": 1,
            }
        ],
    }
    first = await browser.client.post(INTAKE, json=payload, headers=headers)
    assert first.status_code == HTTPStatus.OK
    retry = await browser.client.post(INTAKE, json=payload, headers=headers)
    assert retry.json() == first.json()
    assert first.json()["accepted"] == [str(event_id)]
    async with async_sessionmaker(identity_engine)() as session:
        stored = (await session.scalars(select(ClientObservationRecord))).one()
        source = (await session.scalars(select(DeliverySourceRecord))).one()
        assert source.observation_id == stored.id
        assert not tuple(await session.scalars(select(ProductEventRecord)))
    denied = await browser.client.get(f"/api/v1/operator/delivery-sources/{source.id}")
    assert denied.status_code == HTTPStatus.FORBIDDEN
    inspector = await operator(identity_engine)
    browser.client.cookies.clear()
    browser.client.cookies.set(SESSION_COOKIE, inspector.credential.value)
    found = await browser.client.get(f"/api/v1/operator/delivery-sources/{source.id}")
    assert found.status_code == HTTPStatus.OK
    assert str(event_id) in found.text
    assert found.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("body", "content_type", "status"),
    [
        (b"x" * 16385, "application/json", HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
        (b"{}", "text/plain", HTTPStatus.UNSUPPORTED_MEDIA_TYPE),
    ],
)
async def test_root_observations_apply_raw_body_and_json_bounds_before_parsing(
    browser: BrowserHarness,
    body: bytes,
    content_type: str,
    status: HTTPStatus,
) -> None:
    response = await browser.client.post(
        INTAKE, content=body, headers={"Content-Type": content_type}
    )
    assert response.status_code == status
    assert response.json()["code"] == "command_body_rejected"


async def test_real_worker_registers_destination_and_releases_sql_before_controlled_http(
    identity_engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await actor(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        schema = await session.scalar(select(func.current_schema()))
        event = ProductEventRecord(
            id=uuid4(),
            account_id=owner.id,
            kind="auth.email_confirmed",
            occurrence_key="institutional_binding",
            schema_version=1,
            occurred_at=await session.scalar(select(func.clock_timestamp())),
        )
        session.add(event)
    assert isinstance(schema, str)
    engines: list[AsyncEngine] = []
    stop = asyncio.Event()
    delivered: list[str] = []

    def engine_factory(url: str, **options: object) -> AsyncEngine:
        assert options["pool_size"] == 1
        assert options["max_overflow"] == 0
        assert options["connect_args"] == {
            "timeout": 5,
            "server_settings": {"lock_timeout": "1000"},
        }
        options["connect_args"] = {
            "timeout": 5,
            "server_settings": {"search_path": schema, "lock_timeout": "1000"},
        }
        result = create_async_engine(url, **options)
        engines.append(result)
        return result

    async def provider(request: httpx2.Request) -> httpx2.Response:
        pool = engines[0].pool
        assert isinstance(pool, QueuePool)
        assert pool.checkedout() == 0
        async with sessions() as session:
            assert (await session.scalars(select(DeliveryDestinationRecord))).one().revision == 1
            assert (await session.scalars(select(ExternalDeliveryRecord))).one().state == "leased"
        delivered.append(str(request.url))
        stop.set()
        return httpx2.Response(
            200, json={"cache": "synthetic", "sessionId": str(uuid4()), "visitId": str(uuid4())}
        )

    def transport(_tls: ssl.SSLContext) -> httpx2.AsyncBaseTransport:
        return httpx2.MockTransport(provider)

    monkeypatch.setattr(bootstrap, "create_async_engine", engine_factory)
    monkeypatch.setattr(bootstrap, "_external_transport", transport)
    configuration = ExternalDeliveryWorkerSettings(
        _env_file=None,
        database_url=SecretStr(database_url),
        umami=UmamiDeliveryConfiguration(
            hostname="app.example.test",
            revision=1,
            origin="https://analytics.test",
            website_id=uuid4(),
        ),
    )
    async with asyncio.timeout(10):
        await bootstrap.run_external_delivery_worker(configuration, stop)
    assert delivered == ["https://analytics.test/api/send"]
    async with sessions() as session:
        row = (await session.scalars(select(ExternalDeliveryRecord))).one()
        assert row.state == "succeeded"
        assert row.attempt_count == 1
