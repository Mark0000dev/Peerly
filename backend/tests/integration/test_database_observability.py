"""Real driver events, private payload denial and cancellation with actual pool reuse."""

import asyncio
from http import HTTPStatus

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import event, func, literal, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.infrastructure.observability.database import DatabasePool, DatabaseTelemetry

pytestmark = pytest.mark.integration


async def test_actual_query_events_export_operation_only_and_unregister(
    identity_engine: AsyncEngine,
) -> None:
    exported = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    tracing = TracerProvider(shutdown_on_exit=False)
    tracing.add_span_processor(SimpleSpanProcessor(exported))
    metrics = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    observer = DatabaseTelemetry(tracing.get_tracer("test"), metrics.get_meter("test"))
    observer.attach(identity_engine, DatabasePool.CORE)
    private_marker = "PRIVATE_QUERY_PARAMETER_AND_MESSAGE"
    try:
        async with identity_engine.connect() as connection:
            assert await connection.scalar(select(literal(private_marker))) == private_marker
            assert observer.snapshots[DatabasePool.CORE].checked_out == 1
        assert observer.snapshots[DatabasePool.CORE].checked_out == 0
        with pytest.raises(DBAPIError):
            async with identity_engine.connect() as connection:
                await connection.execute(select(literal(1) / literal(0)))
        spans = exported.get_finished_spans()
        assert spans
        assert all(span.name == "db.query" for span in spans)
        assert all(not span.events and span.status.description is None for span in spans)
        assert all(
            set(span.attributes or {}) == {"db.system", "db.pool.name", "query.operation"}
            for span in spans
        )
        assert private_marker not in repr(spans)
        assert private_marker not in repr(reader.get_metrics_data())
        count = len(spans)
        await identity_engine.dispose()
        observer.close()
        assert not observer.snapshots
        async with identity_engine.connect() as connection:
            await connection.execute(select(literal(private_marker)))
        assert len(exported.get_finished_spans()) == count
    finally:
        observer.close()
        metrics.shutdown()
        tracing.shutdown()


async def test_cancelled_real_query_ends_span_and_releases_pool_without_sdk_sql(
    identity_engine: AsyncEngine,
) -> None:
    exported = InMemorySpanExporter()
    tracing = TracerProvider(shutdown_on_exit=False)
    tracing.add_span_processor(SimpleSpanProcessor(exported))
    observer = DatabaseTelemetry(tracing.get_tracer("test"))
    observer.attach(identity_engine, DatabasePool.CORE)

    async def wait_in_database() -> None:
        async with identity_engine.connect() as connection:
            await connection.execute(select(func.pg_sleep(30)))

    started = asyncio.Event()

    def query_started(**_ignored: object) -> None:
        started.set()

    event.listen(identity_engine.sync_engine, "before_cursor_execute", query_started, named=True)
    task = asyncio.create_task(wait_in_database())
    try:
        async with asyncio.timeout(5):
            await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not observer.engines[0].pending
        assert observer.snapshots[DatabasePool.CORE].checked_out == 0
        assert exported.get_finished_spans()
        async with identity_engine.connect() as connection:
            assert await connection.scalar(select(literal(1))) == 1
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        event.remove(identity_engine.sync_engine, "before_cursor_execute", query_started)
        observer.close()
        tracing.shutdown()


async def test_root_lifespan_owns_hooks_and_sdk_callbacks_never_issue_sql(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient
    from pydantic import SecretStr

    from studymate import bootstrap
    from studymate.config import Settings
    from studymate.infrastructure.observability.runtime import TelemetryRuntime
    from studymate.infrastructure.observability.tracing import OtelHttpTracing

    exported = InMemorySpanExporter()
    tracing = TracerProvider(shutdown_on_exit=False)
    tracing.add_span_processor(SimpleSpanProcessor(exported))
    reader = InMemoryMetricReader()
    metrics = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    runtime = TelemetryRuntime(OtelHttpTracing(), tracing, metrics)
    owners: list[DatabaseTelemetry] = []
    original = bootstrap._database_telemetry

    def observed(value: TelemetryRuntime | None) -> DatabaseTelemetry | None:
        owner = original(value)
        assert owner is not None
        owners.append(owner)
        return owner

    monkeypatch.setattr(bootstrap, "_telemetry", lambda *_args: runtime)
    monkeypatch.setattr(bootstrap, "_database_telemetry", observed)
    app = bootstrap.create_app(Settings(_env_file=None, database_url=SecretStr(database_url)))
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://app.test"
        ) as client:
            result = await client.get("/api/ready")
            assert result.status_code == HTTPStatus.OK
        assert set(owners[0].snapshots) == {DatabasePool.CORE}
        spans_before = exported.get_finished_spans()
        assert spans_before
        assert reader.get_metrics_data() is not None
        assert exported.get_finished_spans() == spans_before
    assert not owners[0].snapshots
    assert not owners[0].engines
