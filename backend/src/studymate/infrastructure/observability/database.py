"""Per-engine public event hooks; never export SQL, parameters or exception text."""

from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from opentelemetry.trace import Span, SpanKind, StatusCode, Tracer
from sqlalchemy import event
from sqlalchemy.engine import Connection, ExceptionContext, ExecutionContext
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import ConnectionPoolEntry, PoolProxiedConnection, QueuePool
from sqlalchemy.sql.ddl import ExecutableDDLElement
from sqlalchemy.sql.dml import Delete, Insert, Update
from sqlalchemy.sql.selectable import SelectBase

_QUERY_KEY = "peerly_observed_query"


class DatabasePool(StrEnum):
    CORE = "core"
    AI_ADMISSION = "ai_admission"
    CHANGE_READ = "change_read"
    EMAIL = "worker_email"
    MEDIA = "worker_media"
    EXPIRY = "worker_expiry"
    CHANGES = "worker_changes"
    AI = "worker_ai"
    EXTERNAL_DELIVERY = "worker_external"


@dataclass(frozen=True, slots=True)
class PoolSnapshot:
    checked_out: int
    configured_size: int | None


@dataclass(frozen=True, slots=True)
class PendingQuery:
    started: float
    operation: str
    span: Span | None


def query_operation(context: ExecutionContext) -> str:
    compiled = context.compiled
    if compiled is None:
        return "other"
    statement = compiled.statement
    for kind, name in (
        (SelectBase, "select"),
        (Insert, "insert"),
        (Update, "update"),
        (Delete, "delete"),
        (ExecutableDDLElement, "ddl"),
    ):
        if isinstance(statement, kind):
            return name
    return "other"


class DatabaseTelemetry:
    """SDK callbacks read cached numbers only; close disables callbacks and every hook."""

    def __init__(self, tracer: Tracer | None = None, meter: Meter | None = None) -> None:
        self.tracer = tracer
        self.duration = meter.create_histogram("db.query.duration", unit="s") if meter else None
        self.snapshots: dict[DatabasePool, PoolSnapshot] = {}
        self.engines: list[EngineObservation] = []
        if meter is not None:
            meter.create_observable_gauge("db.pool.checked_out", callbacks=[self.checked_out])
            meter.create_observable_gauge(
                "db.pool.configured_size", callbacks=[self.configured_size]
            )

    def checked_out(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        return tuple(
            Observation(value.checked_out, {"pool": pool.value})
            for pool, value in tuple(self.snapshots.items())
        )

    def configured_size(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        return tuple(
            Observation(value.configured_size, {"pool": pool.value})
            for pool, value in tuple(self.snapshots.items())
            if value.configured_size is not None
        )

    def attach(self, engine: AsyncEngine, pool: DatabasePool) -> None:
        if pool in self.snapshots or any(value.engine is engine for value in self.engines):
            raise ValueError("Each owned database pool needs a distinct fixed role")
        observation = EngineObservation(self, engine, pool)
        observation.register()
        self.engines.append(observation)

    def close(self) -> None:
        for engine in self.engines:
            engine.close()
        self.engines.clear()
        self.snapshots.clear()


class EngineObservation:
    def __init__(self, owner: DatabaseTelemetry, engine: AsyncEngine, pool: DatabasePool) -> None:
        self.owner, self.engine, self.pool = owner, engine, pool
        self.target_pool = engine.pool
        self.pending: dict[int, PendingQuery] = {}
        self.borrowed: set[int] = set()
        self.configured_size = engine.pool.size() if isinstance(engine.pool, QueuePool) else None
        self.active = False

    def snapshot(self) -> None:
        self.owner.snapshots[self.pool] = PoolSnapshot(len(self.borrowed), self.configured_size)

    def register(self) -> None:
        target = self.engine.sync_engine
        event.listen(target, "before_cursor_execute", self.before, named=True)
        event.listen(target, "after_cursor_execute", self.after, named=True)
        event.listen(target, "handle_error", self.error)
        event.listen(self.target_pool, "checkout", self.checkout)
        event.listen(self.target_pool, "checkin", self.checkin)
        event.listen(self.target_pool, "detach", self.detach)
        event.listen(self.target_pool, "invalidate", self.invalidate)
        self.active = True
        self.snapshot()

    def close(self) -> None:
        if not self.active:
            return
        target = self.engine.sync_engine
        event.remove(target, "before_cursor_execute", self.before)
        event.remove(target, "after_cursor_execute", self.after)
        event.remove(target, "handle_error", self.error)
        event.remove(self.target_pool, "checkout", self.checkout)
        event.remove(self.target_pool, "checkin", self.checkin)
        event.remove(self.target_pool, "detach", self.detach)
        event.remove(self.target_pool, "invalidate", self.invalidate)
        self.active = False
        for key in tuple(self.pending):
            self.finish(key, "closed")
        self.borrowed.clear()
        self.owner.snapshots.pop(self.pool, None)

    def before(self, *, conn: Connection, context: ExecutionContext, **_ignored: object) -> None:
        operation = query_operation(context)
        span = (
            self.owner.tracer.start_span(
                "db.query",
                kind=SpanKind.CLIENT,
                attributes={
                    "db.system": "postgresql",
                    "db.pool.name": self.pool.value,
                    "query.operation": operation,
                },
            )
            if self.owner.tracer
            else None
        )
        key = id(context)
        conn.info[_QUERY_KEY] = key
        self.pending[key] = PendingQuery(perf_counter(), operation, span)

    def after(self, *, context: ExecutionContext, **_ignored: object) -> None:
        self.finish(id(context), "success")

    def error(self, context: ExceptionContext) -> None:
        if context.execution_context is not None:
            self.finish(id(context.execution_context), "error")

    def finish(self, key: int, outcome: str) -> None:
        value = self.pending.pop(key, None)
        if value is None:
            return
        if self.owner.duration is not None:
            self.owner.duration.record(
                max(0, perf_counter() - value.started),
                {
                    "pool": self.pool.value,
                    "operation": value.operation,
                    "outcome": outcome,
                },
            )
        if value.span is not None:
            if outcome != "success":
                value.span.set_status(StatusCode.ERROR)
            value.span.end()

    def checkout(
        self,
        connection: object,
        record: ConnectionPoolEntry,
        proxy: PoolProxiedConnection,
    ) -> None:
        del connection, proxy
        self.borrowed.add(id(record))
        self.snapshot()

    def checkin(self, connection: object, record: ConnectionPoolEntry) -> None:
        del connection
        key = record.info.pop(_QUERY_KEY, None)
        if isinstance(key, int):
            self.finish(key, "cancelled")
        self.borrowed.discard(id(record))
        self.snapshot()

    def detach(self, connection: object, record: ConnectionPoolEntry) -> None:
        self.checkin(connection, record)

    def invalidate(
        self, connection: object, record: ConnectionPoolEntry, error: BaseException | None
    ) -> None:
        del connection, error
        key = record.info.pop(_QUERY_KEY, None)
        if isinstance(key, int):
            self.finish(key, "invalidated")
