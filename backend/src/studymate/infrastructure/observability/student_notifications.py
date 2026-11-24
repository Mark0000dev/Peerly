"""Bounded metadata-only snapshots and actual worker lifecycle observations.

Retained device outcomes are gauges, not attempts counters or device-read receipts.
The SDK never performs SQL; timeout/staleness removes data instead of reporting zero.
"""

import asyncio
import logging
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from typing import Protocol

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from sqlalchemy import func, select, true
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.errors import StorageUnavailableError
from studymate.domain.student_notifications.capabilities import Platform
from studymate.domain.student_notifications.delivery import State
from studymate.infrastructure.observability.delivery_queue import age, count_value
from studymate.infrastructure.observability.logging import LogEvent
from studymate.infrastructure.persistence.transactions import open_transaction
from studymate.infrastructure.student_notifications.capabilities import DeviceAttemptRecord
from studymate.infrastructure.student_notifications.models import DeliveryRecord
from studymate.infrastructure.student_notifications.subscriptions import SubscriptionRecord

INTERVAL_SECONDS = 5.0
TIMEOUT_SECONDS = 0.25
FRESH_SECONDS = 15.0


class DeviceAttemptState(StrEnum):
    SENDING = "sending"
    ACCEPTED = "accepted"
    RETRYABLE = "retryable"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


DEVICE_DIMENSIONS = tuple((platform, enabled) for platform in Platform for enabled in (False, True))
COLUMN_COUNT = len(State) + len(DEVICE_DIMENSIONS) + len(DeviceAttemptState) + 2
SETTINGS = select(
    func.set_config("transaction_read_only", "on", True),
    func.set_config("statement_timeout", "75ms", True),
    func.set_config("lock_timeout", "25ms", True),
)


@dataclass(frozen=True, slots=True)
class NotificationSnapshot:
    queue: tuple[int, ...]
    devices: tuple[int, ...]
    device_attempts: tuple[int, ...]
    oldest_due_seconds: float

    def __post_init__(self) -> None:
        import math

        for values, expected in (
            (self.queue, len(State)),
            (self.devices, len(DEVICE_DIMENSIONS)),
            (self.device_attempts, len(DeviceAttemptState)),
        ):
            if len(values) != expected:
                raise ValueError("Notification snapshot projection changed")
            for value in values:
                count_value(value)
        if not math.isfinite(self.oldest_due_seconds) or self.oldest_due_seconds < 0:
            raise ValueError("Invalid notification due age")


def decode(row: Sequence[object]) -> NotificationSnapshot:
    if len(row) != COLUMN_COUNT:
        raise ValueError("Notification snapshot column count changed")
    q = len(State)
    d = q + len(DEVICE_DIMENSIONS)
    a = d + len(DeviceAttemptState)
    return NotificationSnapshot(
        tuple(count_value(value) for value in row[:q]),
        tuple(count_value(value) for value in row[q:d]),
        tuple(count_value(value) for value in row[d:a]),
        age(row[a + 1], row[a]),
    )


class NotificationReader(Protocol):
    async def snapshot(self) -> NotificationSnapshot: ...


@dataclass(frozen=True, slots=True)
class SqlStudentNotificationReader:
    sessions: async_sessionmaker[AsyncSession] = field(repr=False)

    async def snapshot(self) -> NotificationSnapshot:
        deliveries, devices, attempts = DeliveryRecord, SubscriptionRecord, DeviceAttemptRecord
        queue = select(
            *(
                func.count().filter(deliveries.state == state.value).label(state.value)
                for state in State
            ),
            func.min(deliveries.due_at)
            .filter(
                deliveries.state == State.PENDING.value,
                deliveries.due_at <= func.statement_timestamp(),
            )
            .label("oldest_due"),
        ).subquery()
        registered = select(
            *(
                func.count()
                .filter(devices.platform == platform.value, devices.enabled.is_(enabled))
                .label(f"{platform.value}_{enabled}")
                for platform, enabled in DEVICE_DIMENSIONS
            )
        ).subquery()
        device_attempts = select(
            *(
                func.count().filter(attempts.state == state.value).label(state.value)
                for state in DeviceAttemptState
            )
        ).subquery()
        # Each aggregate yields one row: explicit joins avoid accidental cartesian warnings.
        statement = select(
            *(queue.c[state.value] for state in State),
            *registered.c,
            *device_attempts.c,
            queue.c.oldest_due,
            func.statement_timestamp(),
        ).select_from(queue.join(registered, true()).join(device_attempts, true()))
        try:
            async with open_transaction(self.sessions) as session:
                await session.execute(SETTINGS)
                result = await session.execute(statement)
                row: tuple[object, ...] = tuple(result.one())
            return decode(row)
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) in {"57014", "55P03"}:
                raise StorageUnavailableError from None
            raise


@dataclass(frozen=True, slots=True)
class CachedSnapshot:
    value: NotificationSnapshot
    at: float


class StudentNotificationSignals:
    def __init__(
        self,
        meter: Meter,
        *,
        expected: bool,
        activation_pending: bool = False,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        # Owner supplies actual selected+activated+launch-enabled facts, never timestamp-as-health.
        self._expected = expected
        self._eligible = expected or activation_pending
        self._clock = clock
        self._latest: CachedSnapshot | None = None
        self._valid = False
        self._open = True
        self._running = False
        self._tick_at: float | None = None
        self._storage = False
        self._cycles = meter.create_counter("worker.student_notifications.cycles", unit="{cycle}")
        for name, callback, unit in (
            ("expected", self.expected, ""),
            ("worker.available", self.available, ""),
            ("worker.cycle.age", self.cycle_age, "s"),
            ("sample.fresh", self.fresh, ""),
            ("sample.age", self.sample_age, "s"),
            ("queue.depth", self.depth, ""),
            ("queue.oldest_due", self.oldest, "s"),
            ("devices.count", self.devices, ""),
            ("device_attempts.count", self.device_attempts, ""),
        ):
            meter.create_observable_gauge(
                "worker.student_notifications." + name, callbacks=[callback], unit=unit
            )

    def started(self) -> None:
        if self._open and self._eligible:
            self._running = True
            self._tick_at = None
            self._storage = False

    def activated(self) -> None:
        """A successful canonical materialize proves explicit consumer activation.

        Called only on the selected-provider launch path, never from a historical
        timestamp, process start, sampling result or a delivery acceptance claim.
        """
        if self._open and self._eligible and self._running:
            self._expected = True

    def cycle(self, storage_available: bool) -> None:
        if self._open and self._expected and self._running:
            if not storage_available and (self._tick_at is None or self._storage):
                logging.getLogger("studymate.student_notifications").warning(
                    LogEvent.WORKER_STORAGE_UNAVAILABLE,
                    extra={
                        "event": LogEvent.WORKER_STORAGE_UNAVAILABLE,
                        "worker": "student_notifications",
                        "outcome": "storage_unavailable",
                    },
                )
            self._tick_at = self._clock()
            self._storage = storage_available
            self._cycles.add(1, {"storage": "available" if storage_available else "unavailable"})

    def stopped(self) -> None:
        if self._running:
            logging.getLogger("studymate.student_notifications").info(
                LogEvent.WORKER_STOPPED,
                extra={"event": LogEvent.WORKER_STOPPED, "worker": "student_notifications"},
            )
        self._running = False
        self._storage = False

    def _current(self) -> NotificationSnapshot | None:
        latest = self._latest
        if not self._open or not self._expected or not self._valid or latest is None:
            return None
        return latest.value if 0 <= self._clock() - latest.at <= FRESH_SECONDS else None

    async def sample(self, reader: NotificationReader) -> bool:
        if not self._open or not self._expected:
            return False
        try:
            async with asyncio.timeout(TIMEOUT_SECONDS):
                snapshot = await reader.snapshot()
        except (StorageUnavailableError, TimeoutError):
            self._valid = False
            return False
        except asyncio.CancelledError:
            self._valid = False
            raise
        self._latest = CachedSnapshot(snapshot, self._clock())
        self._valid = True
        return True

    async def run(self, reader: NotificationReader, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                await self.sample(reader)
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), INTERVAL_SECONDS)
        finally:
            self.close()

    def close(self) -> None:
        self.stopped()
        self._open = False
        self._valid = False

    def expected(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        return (Observation(int(self._expected)),) if self._open else ()

    def available(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        if not self._open or not self._expected:
            return ()
        fresh = self._tick_at is not None and 0 <= self._clock() - self._tick_at <= FRESH_SECONDS
        return (Observation(int(self._running and self._storage and fresh)),)

    def cycle_age(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        at = self._tick_at
        return (
            ()
            if not self._open or not self._expected or at is None
            else (Observation(max(0.0, self._clock() - at)),)
        )

    def fresh(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        return (
            (Observation(int(self._current() is not None)),)
            if self._open and self._expected
            else ()
        )

    def sample_age(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        latest = self._latest
        return (
            ()
            if not self._open or not self._expected or latest is None
            else (Observation(max(0.0, self._clock() - latest.at)),)
        )

    def depth(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        snapshot = self._current()
        return (
            ()
            if snapshot is None
            else tuple(
                Observation(value, {"state": state.value})
                for state, value in zip(State, snapshot.queue, strict=True)
            )
        )

    def oldest(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        snapshot = self._current()
        return () if snapshot is None else (Observation(snapshot.oldest_due_seconds),)

    def devices(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        snapshot = self._current()
        return (
            ()
            if snapshot is None
            else tuple(
                Observation(value, {"platform": platform.value, "enabled": str(enabled).lower()})
                for (platform, enabled), value in zip(
                    DEVICE_DIMENSIONS, snapshot.devices, strict=True
                )
            )
        )

    def device_attempts(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        snapshot = self._current()
        return (
            ()
            if snapshot is None
            else tuple(
                Observation(value, {"state": state.value})
                for state, value in zip(DeviceAttemptState, snapshot.device_attempts, strict=True)
            )
        )
