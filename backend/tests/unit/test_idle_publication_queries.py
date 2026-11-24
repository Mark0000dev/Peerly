"""Actual SDK export/metrics; database-hook boundary units, no SQL/PG substitute."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import pytest
from opentelemetry.context import Context
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import Histogram, InMemoryMetricReader, Sum
from opentelemetry.sdk.trace import Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.changes.loop import ChangeMaintenance
from studymate.infrastructure.observability.changes import ObservedChangeStep
from studymate.infrastructure.observability.database import (
    DatabasePool,
    DatabaseTelemetry,
    EngineObservation,
)
from studymate.infrastructure.observability.idle_publication import (
    MAX_DEFERRED_QUERIES,
    defer_empty_publication,
    publication_queries,
)


class CreatedSpans(SpanProcessor):
    def __init__(self) -> None:
        self.names: list[str] = []

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        del parent_context
        self.names.append(span.name)


@dataclass(frozen=True)
class Signals:
    tracing: TracerProvider
    created: CreatedSpans
    spans: InMemorySpanExporter
    meter: MeterProvider
    reader: InMemoryMetricReader
    database: DatabaseTelemetry
    observation: EngineObservation
    engine: AsyncEngine

    def query(self, operation: str = "select", outcome: str = "success") -> None:
        # Exercise the common query hook's pure begin/finish boundary. No mocked
        # SQL result is offered as evidence for repository/PostgreSQL behavior.
        self.observation.pending[1] = self.observation.begin(operation)
        self.observation.finish(1, outcome)

    def count(self, name: str, **dimensions: str) -> int:
        data = self.reader.get_metrics_data()
        assert data is not None
        count = 0
        for resource in data.resource_metrics:
            for scope in resource.scope_metrics:
                for metric in scope.metrics:
                    if metric.name != name:
                        continue
                    if isinstance(metric.data, Sum):
                        for point in metric.data.data_points:
                            if all(
                                (point.attributes or {}).get(k) == v for k, v in dimensions.items()
                            ):
                                count += int(point.value)
                    elif isinstance(metric.data, Histogram):
                        for histogram_point in metric.data.data_points:
                            if all(
                                (histogram_point.attributes or {}).get(k) == v
                                for k, v in dimensions.items()
                            ):
                                count += histogram_point.count
        return count


@pytest.fixture
async def signals() -> AsyncIterator[Signals]:
    spans = InMemorySpanExporter()
    tracing = TracerProvider(shutdown_on_exit=False)
    tracing.add_span_processor(SimpleSpanProcessor(spans))
    created = CreatedSpans()
    tracing.add_span_processor(created)
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    database = DatabaseTelemetry(tracing.get_tracer("unit"), meter.get_meter("unit"))
    # Engine construction does not connect. No DB, provider or credentials used.
    engine = create_async_engine("postgresql+asyncpg://unit:unit@localhost/never_connected_test")
    observation = EngineObservation(database, engine, DatabasePool.CHANGES)
    try:
        yield Signals(tracing, created, spans, meter, reader, database, observation, engine)
    finally:
        await engine.dispose()
        database.close()
        meter.shutdown()
        tracing.shutdown()


def observed(
    signals: Signals, step: "Step", kind: ChangeMaintenance = ChangeMaintenance.PUBLICATION
) -> ObservedChangeStep:
    return ObservedChangeStep(
        step, kind, signals.tracing.get_tracer("unit"), signals.meter.get_meter("unit")
    )


# A typed alias keeps tests within the same public callback contract as the worker.

Step = Callable[[], Awaitable[int]]


async def test_empty_publication_creates_no_spans_but_retains_every_idle_and_db_metric(
    signals: Signals,
) -> None:
    async def empty() -> int:
        signals.query()
        return 0

    polls = 5
    for _ in range(polls):
        assert await observed(signals, empty)() == 0
    assert not signals.spans.get_finished_spans()
    assert not signals.created.names
    assert signals.count("db.query.duration", pool="worker_changes", outcome="success") == polls
    assert signals.count("worker.changes.steps", maintenance="publication", outcome="idle") == polls
    assert signals.count("worker.changes.duration", outcome="idle") == polls
    assert publication_queries() is None


async def test_actual_work_retains_query_spans_and_real_execution_times(signals: Signals) -> None:
    async def work() -> int:
        signals.query()
        signals.query("update")
        return 1

    assert await observed(signals, work)() == 1
    spans = signals.spans.get_finished_spans()
    expected_queries = 2
    assert [span.name for span in spans].count("db.query") == expected_queries
    worker = next(span for span in spans if span.name == "changes.publication")
    assert worker.start_time is not None
    assert worker.end_time is not None
    for span in spans:
        assert span.start_time is not None
        assert span.end_time is not None
        assert worker.start_time <= span.start_time <= span.end_time <= worker.end_time
    assert signals.count("worker.changes.hints") == 1


@pytest.mark.parametrize("failure", ["storage", "unexpected", "cancelled"])
async def test_empty_query_before_failure_is_exported_and_exception_preserved(
    signals: Signals, failure: str
) -> None:
    error = (
        StorageUnavailableError("synthetic-private")
        if failure == "storage"
        else asyncio.CancelledError("synthetic-private")
        if failure == "cancelled"
        else RuntimeError("synthetic-private")
    )

    async def fail() -> int:
        signals.query()
        raise error

    with pytest.raises(type(error)) as caught:
        await observed(signals, fail)()
    assert caught.value is error
    spans = signals.spans.get_finished_spans()
    assert {span.name for span in spans} == {"db.query", "changes.publication"}
    assert "synthetic-private" not in repr(spans)
    assert all(not span.events for span in spans)
    assert (
        next(span for span in spans if span.name == "changes.publication").status.status_code
        == StatusCode.ERROR
    )
    assert signals.count("db.query.duration") == 1


@pytest.mark.parametrize("outcome", ["error", "cancelled", "invalidated", "closed"])
async def test_query_failure_is_never_hidden_by_idle_return(signals: Signals, outcome: str) -> None:
    async def recovered() -> int:
        signals.query(outcome=outcome)
        return 0

    assert await observed(signals, recovered)() == 0
    (span,) = signals.spans.get_finished_spans()
    assert span.name == "db.query"
    assert span.status.status_code == StatusCode.ERROR
    assert signals.count("db.query.duration", outcome=outcome) == 1


@pytest.mark.parametrize("count", [-1, True])
async def test_invalid_worker_result_preserves_query_and_failure(
    signals: Signals, count: int
) -> None:
    async def invalid() -> int:
        signals.query()
        return count

    with pytest.raises(RuntimeError):
        await observed(signals, invalid)()
    expected_spans = 2
    assert len(signals.spans.get_finished_spans()) == expected_spans


async def test_write_with_zero_result_is_unproven_idle_and_retains_all_queries(
    signals: Signals,
) -> None:
    async def write() -> int:
        signals.query()
        signals.query("delete")
        return 0

    assert await observed(signals, write)() == 0
    expected_spans = 2
    assert len(signals.spans.get_finished_spans()) == expected_spans


async def test_retention_and_other_pool_queries_are_unchanged(signals: Signals) -> None:
    async def idle() -> int:
        signals.query()
        return 0

    await observed(signals, idle, ChangeMaintenance.RETENTION)()
    core = EngineObservation(signals.database, signals.engine, DatabasePool.CORE)

    async def unrelated() -> int:
        core.pending[1] = core.begin("select")
        core.finish(1, "success")
        return 0

    await observed(signals, unrelated)()
    spans = signals.spans.get_finished_spans()
    expected_spans = 2
    assert len(spans) == expected_spans
    assert {span.attributes["db.pool.name"] for span in spans if span.attributes} == {
        "core",
        "worker_changes",
    }


async def test_user_action_parent_and_context_are_preserved(signals: Signals) -> None:
    async def idle() -> int:
        signals.query()
        return 0

    with signals.tracing.get_tracer("unit").start_as_current_span("user-action") as actor:
        await observed(signals, idle)()
        actor_context = actor.get_span_context()
    query = next(span for span in signals.spans.get_finished_spans() if span.name == "db.query")
    assert query.parent == actor_context
    assert query.context is not None
    assert query.context.trace_id == actor_context.trace_id
    assert publication_queries() is None


async def test_child_task_does_not_inherit_permission_to_suppress_spans(signals: Signals) -> None:
    async def child() -> None:
        signals.query()

    async def idle() -> int:
        await asyncio.create_task(child())
        return 0

    await observed(signals, idle)()
    assert len(signals.spans.get_finished_spans()) == 1


async def test_overflow_fails_open_without_unbounded_buffer_or_span_loss(signals: Signals) -> None:
    async def idle() -> int:
        for _ in range(MAX_DEFERRED_QUERIES + 2):
            signals.query()
        return 0

    await observed(signals, idle)()
    assert len(signals.spans.get_finished_spans()) == MAX_DEFERRED_QUERIES + 2


async def test_unfinished_query_is_retained_when_it_completes_after_scope(signals: Signals) -> None:
    with defer_empty_publication() as scope:
        signals.observation.pending[1] = signals.observation.begin("select")
        scope.empty = True
    signals.observation.finish(1, "cancelled")
    assert len(signals.spans.get_finished_spans()) == 1


async def test_concurrent_empty_and_working_polls_do_not_share_scope(signals: Signals) -> None:
    async def empty() -> int:
        signals.query()
        await asyncio.sleep(0)
        return 0

    async def work() -> int:
        signals.query()
        await asyncio.sleep(0)
        return 1

    empty_result, work_result = await asyncio.gather(
        observed(signals, empty)(), observed(signals, work)()
    )
    assert empty_result == 0
    assert work_result == 1
    assert [span.name for span in signals.spans.get_finished_spans()].count("db.query") == 1
    expected_queries = 2
    assert signals.count("db.query.duration") == expected_queries


async def test_exception_after_empty_confirmation_still_retains_queries(signals: Signals) -> None:
    def fail_after_confirmation() -> None:
        with defer_empty_publication() as scope:
            signals.query()
            scope.empty = True
            raise RuntimeError("synthetic-failure")

    with pytest.raises(RuntimeError, match="synthetic-failure"):
        fail_after_confirmation()
    assert len(signals.spans.get_finished_spans()) == 1
    assert publication_queries() is None
