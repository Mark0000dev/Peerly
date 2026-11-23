"""Real PostgreSQL publication queries preserve work and failure telemetry."""

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from sqlalchemy import literal, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.changes.publication import PublishChanges
from studymate.infrastructure.changes.loop import ChangeMaintenance
from studymate.infrastructure.changes.publication import SqlChangePublicationUnitOfWork
from studymate.infrastructure.observability.changes import ObservedChangeStep
from studymate.infrastructure.observability.database import DatabasePool, DatabaseTelemetry

pytestmark = pytest.mark.integration


async def test_real_empty_publication_has_no_query_span_but_real_work_and_errors_do(
    identity_engine: AsyncEngine,
) -> None:
    exporter = InMemorySpanExporter()
    tracing = TracerProvider(shutdown_on_exit=False)
    tracing.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = tracing.get_tracer("integration")
    database = DatabaseTelemetry(tracer)
    database.attach(identity_engine, DatabasePool.CHANGES)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    try:
        publish = PublishChanges(SqlChangePublicationUnitOfWork(sessions))
        assert await ObservedChangeStep(publish, ChangeMaintenance.PUBLICATION, tracer)() == 0
        assert not exporter.get_finished_spans()

        async def work() -> int:
            async with identity_engine.connect() as connection:
                assert await connection.scalar(select(literal(1))) == 1
            return 1

        assert await ObservedChangeStep(work, ChangeMaintenance.PUBLICATION, tracer)() == 1
        assert {span.name for span in exporter.get_finished_spans()} == {
            "db.query",
            "changes.publication",
        }
        exporter.clear()

        async def fail() -> int:
            async with identity_engine.connect() as connection:
                await connection.execute(select(literal(1) / literal(0)))
            return 0

        with pytest.raises(DBAPIError):
            await ObservedChangeStep(fail, ChangeMaintenance.PUBLICATION, tracer)()
        spans = exporter.get_finished_spans()
        assert {span.name for span in spans} == {"db.query", "changes.publication"}
        assert all(span.status.status_code == StatusCode.ERROR for span in spans)
        assert all(not span.events and span.status.description is None for span in spans)
    finally:
        database.close()
        tracing.shutdown()
