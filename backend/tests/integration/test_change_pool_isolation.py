"""Controlled exhausted transport pool; not500 live authorized SSE connections."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
from starlette.types import Message, Scope

from studymate.application.changes.observations import (
    StreamEnd,
    StreamFrame,
    StreamObservation,
    StreamSend,
)
from studymate.application.changes.reads import ReadChanges
from studymate.application.check_readiness import CheckReadiness
from studymate.bootstrap import create_change_read_engine, create_changes_worker_engine
from studymate.infrastructure.changes.reads import SqlChangeReadUnitOfWork
from studymate.infrastructure.persistence.database import SqlDatabaseProbe
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.changes.router import ChangeHttpServices, changes_router
from studymate.presentation.changes.stream import ChangeStreamPolicy
from studymate.presentation.health import health_router
from tests.integration.requests.fixture import HASHER
from tests.integration.test_message_commands import chat

pytestmark = pytest.mark.integration
BURST_SIZE = 500
CORE_READS = 12
STREAM_READ_CONNECTIONS = 2
CORE_LATENCY_BUDGET_SECONDS = 2.0
BURST_SEND_TIMEOUT_SECONDS = 0.1
PRODUCTION_SEND_TIMEOUT_SECONDS = 5.0


@dataclass(slots=True)
class BurstStreamObservations:
    opened_count: int = 0
    closed_reasons: list[StreamEnd] = field(default_factory=list)
    sends: list[tuple[float, StreamSend]] = field(default_factory=list)
    delivered_frames: list[tuple[StreamFrame, datetime | None]] = field(default_factory=list)

    def stream(self) -> StreamObservation:
        return self

    def opened(self) -> None:
        self.opened_count += 1

    def closed(self, reason: StreamEnd) -> None:
        self.closed_reasons.append(reason)

    def frame(self, kind: StreamFrame, published_at: datetime | None = None) -> None:
        self.delivered_frames.append((kind, published_at))

    def sent(self, seconds: float, *, outcome: StreamSend) -> None:
        self.sends.append((seconds, outcome))


def assert_burst_isolated(
    starts: list[int],
    core_durations: list[float],
    observations: BurstStreamObservations,
    pool: AsyncAdaptedQueuePool,
    stalled: asyncio.Event,
) -> None:
    assert ChangeStreamPolicy().send_timeout_seconds == PRODUCTION_SEND_TIMEOUT_SECONDS
    assert len(starts) == BURST_SIZE
    assert 0 < starts.count(HTTPStatus.OK) <= BURST_SIZE
    assert set(starts) <= {HTTPStatus.OK, HTTPStatus.SERVICE_UNAVAILABLE}
    assert len(core_durations) == CORE_READS
    assert max(core_durations) < CORE_LATENCY_BUDGET_SECONDS
    admitted = starts.count(HTTPStatus.OK)
    assert stalled.is_set()
    assert observations.opened_count == admitted
    assert observations.closed_reasons == [StreamEnd.BACKPRESSURE] * admitted
    assert len(observations.sends) == admitted
    assert all(outcome == StreamSend.TIMEOUT for _, outcome in observations.sends)
    assert not observations.delivered_frames
    assert pool.size() == STREAM_READ_CONNECTIONS
    assert pool.checkedout() == 0
    assert pool.overflow() == 0


def record_burst_properties(
    record: Callable[[str, object], None],
    observations: BurstStreamObservations,
    starts: list[int],
    core_durations: list[float],
    admission_seconds: float | None,
) -> None:
    record("headers_seen", len(starts))
    record("admitted_streams", starts.count(HTTPStatus.OK))
    record("backpressure_closed", observations.closed_reasons.count(StreamEnd.BACKPRESSURE))
    record("cancelled_streams", observations.closed_reasons.count(StreamEnd.CANCELLED))
    record("admission_seconds", admission_seconds)
    record("core_completed", len(core_durations))
    record("core_max_seconds", max(core_durations) if core_durations else None)


async def test_exhausted_change_pool_sheds_burst_without_consuming_core_or_worker_connections(
    identity_engine: AsyncEngine,
    database_url: str,
) -> None:
    owned = await chat(identity_engine)
    async with identity_engine.connect() as connection:
        schema = await connection.scalar(select(func.current_schema()))
    assert isinstance(schema, str)
    transport = create_change_read_engine(database_url, server_settings={"search_path": schema})
    worker = create_changes_worker_engine(database_url, server_settings={"search_path": schema})
    assert transport.pool is not identity_engine.pool
    assert worker.pool is not transport.pool
    assert isinstance(transport.pool, AsyncAdaptedQueuePool)
    assert isinstance(worker.pool, AsyncAdaptedQueuePool)
    assert transport.pool.size() == STREAM_READ_CONNECTIONS
    assert worker.pool.size() == 1
    reader = ReadChanges(
        SqlChangeReadUnitOfWork(async_sessionmaker(transport, expire_on_commit=False)), HASHER
    )
    app = FastAPI()
    app.include_router(changes_router(ChangeHttpServices(reader)))
    app.include_router(
        health_router(CheckReadiness(SqlDatabaseProbe(async_sessionmaker(identity_engine))))
    )
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="https://peerly.test") as client,
        ):
            client.cookies.set(SESSION_COOKIE, owned.recipient.credential.value)
            async with transport.connect(), transport.connect():

                async def rejected_stream() -> None:
                    response = await client.get("/api/v1/events")
                    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
                    assert response.json()["code"] == "storage_unavailable"
                    assert response.headers["Retry-After"] == "1"
                    assert "asyncpg" not in response.text

                async def healthy_core() -> None:
                    response = await client.get("/api/ready")
                    assert response.status_code == HTTPStatus.OK

                async def healthy_worker() -> None:
                    async with worker.connect() as connection:
                        assert await connection.scalar(select(1)) == 1

                async with asyncio.timeout(5):
                    await asyncio.gather(
                        *(rejected_stream() for _ in range(BURST_SIZE)),
                        *(healthy_core() for _ in range(CORE_READS)),
                        healthy_worker(),
                    )
                assert transport.pool.checkedout() == transport.pool.size()
                assert transport.pool.overflow() == 0
            # Releasing the exhausted pool permits a genuine authorized SQL read again.
            page = await reader(owned.recipient.credential, None)
            assert page.reset_required
            assert not page.changes
            assert not page.has_more
    finally:
        await transport.dispose()
        await worker.dispose()


async def test_burst_of500_hot_account_stream_attempts_keeps_positive_bounded_admission(
    identity_engine: AsyncEngine,
    database_url: str,
    record_property: Callable[[str, object], None],
) -> None:
    """500 ASGI clients share two real accounts, not500 independent student identities."""
    owned = await chat(identity_engine)
    async with identity_engine.connect() as connection:
        schema = await connection.scalar(select(func.current_schema()))
    assert isinstance(schema, str)
    transport = create_change_read_engine(database_url, server_settings={"search_path": schema})
    reader = ReadChanges(
        SqlChangeReadUnitOfWork(async_sessionmaker(transport, expire_on_commit=False)), HASHER
    )
    app = FastAPI()
    observations = BurstStreamObservations()
    # Exercise the real bounded-send path with an explicit short test policy.
    # Keep the admission watchdog independent of production-length send expiry;
    # production stays5s, and every admitted stream must end via a real timeout.
    policy = ChangeStreamPolicy(send_timeout_seconds=BURST_SEND_TIMEOUT_SECONDS)
    app.include_router(changes_router(ChangeHttpServices(reader, policy, observations)))
    starts: list[int] = []
    core_durations: list[float] = []
    never = asyncio.Event()
    stalled = asyncio.Event()
    loop = asyncio.get_running_loop()
    admission_finished_at: float | None = None

    async def attempt_stream(index: int) -> None:
        actor = owned.sender if index % 2 else owned.recipient
        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/events",
            "raw_path": b"/api/v1/events",
            "query_string": b"",
            "root_path": "",
            "client": ("127.0.0.1", index),
            "server": ("peerly.test", 443),
            "headers": [(b"cookie", f"{SESSION_COOKIE}={actor.credential.value}".encode())],
        }
        status: int | None = None

        async def receive() -> Message:
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            nonlocal status, admission_finished_at
            if message["type"] == "http.response.start":
                status = message["status"]
                starts.append(status)
                if len(starts) == BURST_SIZE:
                    admission_finished_at = loop.time()
            elif message["type"] == "http.response.body" and status == HTTPStatus.OK:
                # A slow network send must hold no SQL lease while its deadline elapses.
                stalled.set()
                await never.wait()

        await app(scope, receive, send)

    async def core_read() -> None:
        # A real admitted send must already be stalled when core probes begin.
        await stalled.wait()
        started = loop.time()
        assert await SqlDatabaseProbe(owned.api.sessions).is_available()
        core_durations.append(loop.time() - started)

    burst_started = loop.time()
    try:
        async with app.router.lifespan_context(app), asyncio.timeout(10):
            await asyncio.gather(
                *(attempt_stream(index) for index in range(BURST_SIZE)),
                *(core_read() for _ in range(CORE_READS)),
            )
        assert isinstance(transport.pool, AsyncAdaptedQueuePool)
        assert_burst_isolated(starts, core_durations, observations, transport.pool, stalled)
    finally:
        record_burst_properties(
            record_property,
            observations,
            starts,
            core_durations,
            admission_finished_at - burst_started if admission_finished_at is not None else None,
        )
        record_property("send_timeout_seconds", policy.send_timeout_seconds)
        await transport.dispose()
