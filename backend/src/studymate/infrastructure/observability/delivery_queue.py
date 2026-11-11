"""Bounded exact outbox reads; SDK callbacks only read fresh immutable snapshots.

Exact counts are not constant-cost with retained history. Budget exhaustion is
unknown, never an empty queue or an undisclosed lower bound.
"""

import asyncio
import math
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from time import monotonic
from typing import Protocol

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.domain.external_delivery.delivery import FailureCode
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.external_delivery.models import (
    DeliveryScheduleRecord,
    DeliverySourceRecord,
    ExternalDeliveryRecord,
)
from studymate.infrastructure.persistence.transactions import open_transaction

SAMPLE_INTERVAL_SECONDS = 5.0
SAMPLE_TIMEOUT_SECONDS = 0.25
SAMPLE_FRESH_SECONDS = 15.0
STATES = ("pending", "retry", "dead")
EXPECTED_COLUMNS = 9
EXPECTED_QUERY_TIMEOUTS = frozenset({"57014", "55P03"})


@dataclass(frozen=True, slots=True)
class SinkQueueSnapshot:
    sink: Sink
    pending: int
    retry: int
    dead: int
    oldest_due_seconds: float
    blocked_reason: FailureCode | None


@dataclass(frozen=True, slots=True)
class DeliveryQueueSnapshot:
    sinks: tuple[SinkQueueSnapshot, ...]
    sources_pending: int
    sources_oldest_seconds: float

    def __post_init__(self) -> None:
        if len(self.sinks) != len(Sink) or {item.sink for item in self.sinks} != set(Sink):
            raise ValueError("Delivery queue observation requires both seeded sinks")


class DeliveryQueueReader(Protocol):
    async def snapshot(self) -> DeliveryQueueSnapshot: ...


def count_value(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Invalid exact delivery queue count")
    return value


def age(at: object, before: object) -> float:
    if not isinstance(at, datetime) or at.tzinfo is None:
        raise ValueError("Delivery observation requires actual database time")
    if before is None:
        return 0.0
    if not isinstance(before, datetime) or before.tzinfo is None:
        raise ValueError("Delivery observation requires an aware source time")
    seconds = max(0.0, (at - before).total_seconds())
    if not math.isfinite(seconds):
        raise ValueError("Invalid delivery queue age")
    return seconds


def decode(rows: Sequence[Sequence[object]]) -> DeliveryQueueSnapshot:
    sinks = []
    source_counts: set[int] = set()
    source_ages: set[float] = set()
    for row in rows:
        if len(row) != EXPECTED_COLUMNS:
            raise ValueError("Delivery queue projection changed")
        sink, pending, retry, dead, due, blocked, at, source_count, source_oldest = row
        if not isinstance(sink, str) or (blocked is not None and not isinstance(blocked, str)):
            raise ValueError("Invalid delivery schedule observation")
        sinks.append(
            SinkQueueSnapshot(
                Sink(sink),
                count_value(pending),
                count_value(retry),
                count_value(dead),
                age(at, due),
                FailureCode(blocked) if blocked is not None else None,
            )
        )
        source_counts.add(count_value(source_count))
        source_ages.add(age(at, source_oldest))
    if len(source_counts) != 1 or len(source_ages) != 1:
        raise ValueError("Delivery source observations lost their atomic snapshot")
    return DeliveryQueueSnapshot(tuple(sinks), source_counts.pop(), source_ages.pop())


@dataclass(frozen=True, slots=True)
class SqlDeliveryQueueReader:
    sessions: async_sessionmaker[AsyncSession] = field(repr=False)

    async def snapshot(self) -> DeliveryQueueSnapshot:
        deliveries = ExternalDeliveryRecord
        counts = (
            select(
                deliveries.sink.label("sink"),
                *(func.count().filter(deliveries.state == state).label(state) for state in STATES),
            )
            .where(deliveries.state.in_(STATES))
            .group_by(deliveries.sink)
            .subquery()
        )
        due = (
            select(deliveries.next_attempt_at)
            .where(
                deliveries.sink == DeliveryScheduleRecord.sink,
                # Static predicate matches the existing partial index even with a generic plan.
                text("external_deliveries.state IN ('pending','retry')"),
                deliveries.next_attempt_at <= func.statement_timestamp(),
            )
            .order_by(deliveries.next_attempt_at, deliveries.id)
            .limit(1)
            .scalar_subquery()
        )
        source_count = (
            select(func.count())
            .select_from(DeliverySourceRecord)
            .where(DeliverySourceRecord.materialized_at.is_(None))
            .scalar_subquery()
        )
        source_oldest = (
            select(DeliverySourceRecord.captured_at)
            .where(DeliverySourceRecord.materialized_at.is_(None))
            .order_by(DeliverySourceRecord.captured_at, DeliverySourceRecord.id)
            .limit(1)
            .scalar_subquery()
        )
        statement = (
            select(
                DeliveryScheduleRecord.sink,
                *(func.coalesce(counts.c[state], 0) for state in STATES),
                due,
                DeliveryScheduleRecord.blocked_reason,
                func.statement_timestamp(),
                source_count,
                source_oldest,
            )
            .outerjoin(counts, counts.c.sink == DeliveryScheduleRecord.sink)
            .order_by(DeliveryScheduleRecord.sink)
        )
        try:
            async with open_transaction(self.sessions) as session:
                await session.execute(text("SET TRANSACTION READ ONLY"))
                await session.execute(text("SET LOCAL statement_timeout = '75ms'"))
                await session.execute(text("SET LOCAL lock_timeout = '25ms'"))
                result = await session.execute(statement)
                rows: tuple[Sequence[object], ...] = tuple(tuple(row) for row in result)
            return decode(rows)
        except DBAPIError as error:
            sqlstate: object = getattr(error.orig, "sqlstate", None)
            if isinstance(sqlstate, str) and sqlstate in EXPECTED_QUERY_TIMEOUTS:
                raise StorageUnavailableError from None
            raise


@dataclass(frozen=True, slots=True)
class CachedDeliveryQueue:
    snapshot: DeliveryQueueSnapshot
    observed_at: float


class DeliveryQueueSignals:
    def __init__(self, meter: Meter, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._latest: CachedDeliveryQueue | None = None
        self._enabled = True
        self._valid = False
        meter.create_observable_gauge("worker.external.queue.depth", callbacks=[self.depth])
        meter.create_observable_gauge(
            "worker.external.queue.oldest_due", callbacks=[self.oldest], unit="s"
        )
        meter.create_observable_gauge("worker.external.queue.blocked", callbacks=[self.blocked])
        meter.create_observable_gauge("worker.external.queue.sample.fresh", callbacks=[self.fresh])
        meter.create_observable_gauge(
            "worker.external.queue.sample.age", callbacks=[self.sample_age], unit="s"
        )
        meter.create_observable_gauge(
            "worker.external.sources.pending", callbacks=[self.sources_pending]
        )
        meter.create_observable_gauge(
            "worker.external.sources.oldest", callbacks=[self.sources_oldest], unit="s"
        )

    def _current(self) -> DeliveryQueueSnapshot | None:
        latest = self._latest
        if not self._enabled or not self._valid or latest is None:
            return None
        if not 0 <= self._clock() - latest.observed_at <= SAMPLE_FRESH_SECONDS:
            return None
        return latest.snapshot

    async def sample(self, reader: DeliveryQueueReader) -> bool:
        if not self._enabled:
            return False
        try:
            async with asyncio.timeout(SAMPLE_TIMEOUT_SECONDS):
                snapshot = await reader.snapshot()
        except (StorageUnavailableError, TimeoutError):
            self._valid = False
            return False
        except asyncio.CancelledError:
            self._valid = False
            raise
        self._latest = CachedDeliveryQueue(snapshot, self._clock())
        self._valid = True
        return True

    async def run(self, reader: DeliveryQueueReader, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                await self.sample(reader)
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), SAMPLE_INTERVAL_SECONDS)
        finally:
            self.close()

    def close(self) -> None:
        self._enabled = False
        self._valid = False

    def depth(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        snapshot = self._current()
        return (
            ()
            if snapshot is None
            else tuple(
                Observation(value, {"sink": item.sink.value, "state": state})
                for item in snapshot.sinks
                for state, value in zip(STATES, (item.pending, item.retry, item.dead), strict=True)
            )
        )

    def oldest(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        snapshot = self._current()
        return (
            ()
            if snapshot is None
            else tuple(
                Observation(item.oldest_due_seconds, {"sink": item.sink.value})
                for item in snapshot.sinks
            )
        )

    def blocked(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        snapshot = self._current()
        return (
            ()
            if snapshot is None
            else tuple(
                Observation(
                    int(item.blocked_reason == reason),
                    {"sink": item.sink.value, "reason": reason.value},
                )
                for item in snapshot.sinks
                for reason in FailureCode
            )
        )

    def fresh(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        return (Observation(int(self._current() is not None)),) if self._enabled else ()

    def sample_age(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        latest = self._latest
        return (
            ()
            if not self._enabled or latest is None
            else (Observation(max(0.0, self._clock() - latest.observed_at)),)
        )

    def sources_pending(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        snapshot = self._current()
        return () if snapshot is None else (Observation(snapshot.sources_pending),)

    def sources_oldest(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        snapshot = self._current()
        return () if snapshot is None else (Observation(snapshot.sources_oldest_seconds),)
