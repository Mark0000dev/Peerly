"""Freshness, finite labels and truthful worker lifecycle; no database/provider."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from opentelemetry.metrics import CallbackOptions
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from studymate.application.errors import StorageUnavailableError
from studymate.domain.student_notifications.delivery import State
from studymate.infrastructure.observability.student_notifications import (
    DEVICE_DIMENSIONS,
    DeviceAttemptState,
    NotificationSnapshot,
    StudentNotificationSignals,
    decode,
)

STALE_AGE = 16
DUE_AGE = 30


def snapshot(value: int = 1) -> NotificationSnapshot:
    return NotificationSnapshot(
        (value,) * len(State),
        (value,) * len(DEVICE_DIMENSIONS),
        (value,) * len(DeviceAttemptState),
        60.0,
    )


@dataclass(slots=True)
class Reader:
    value: NotificationSnapshot = field(default_factory=snapshot)
    unavailable: bool = False
    calls: int = 0

    async def snapshot(self) -> NotificationSnapshot:
        self.calls += 1
        if self.unavailable:
            raise StorageUnavailableError
        return self.value


async def test_unconfigured_is_not_down_and_never_reads_or_reports_data() -> None:
    provider = MeterProvider(shutdown_on_exit=False)
    signals = StudentNotificationSignals(provider.get_meter("test"), expected=False)
    reader = Reader()
    options = CallbackOptions()
    try:
        assert not await signals.sample(reader)
        signals.started()
        signals.cycle(True)
        assert reader.calls == 0
        assert signals.expected(options)[0].value == 0
        for callback in (
            signals.available,
            signals.depth,
            signals.devices,
            signals.device_attempts,
            signals.fresh,
            signals.oldest,
            signals.sample_age,
            signals.cycle_age,
        ):
            assert callback(options) == ()
    finally:
        signals.close()
        provider.shutdown()


async def test_failed_stale_and_backwards_clock_samples_are_unknown_then_recover() -> None:
    provider = MeterProvider(shutdown_on_exit=False)
    clock = [100.0]
    signals = StudentNotificationSignals(
        provider.get_meter("test"), expected=True, clock=lambda: clock[0]
    )
    reader = Reader()
    options = CallbackOptions()
    try:
        assert signals.depth(options) == ()
        assert signals.fresh(options)[0].value == 0
        assert await signals.sample(reader)
        assert sum(item.value for item in signals.depth(options)) == len(State)
        reader.unavailable = True
        assert not await signals.sample(reader)
        assert signals.depth(options) == ()
        assert signals.devices(options) == ()
        assert signals.device_attempts(options) == ()
        reader.unavailable = False
        reader.value = snapshot(0)
        assert await signals.sample(reader)
        assert all(item.value == 0 for item in signals.depth(options))
        clock[0] += STALE_AGE
        assert signals.depth(options) == ()
        assert signals.fresh(options)[0].value == 0
        clock[0] = 99
        assert signals.depth(options) == ()
    finally:
        signals.close()
        provider.shutdown()


async def test_health_requires_actual_completed_cycle_not_start_or_historical_activation() -> None:
    provider = MeterProvider(shutdown_on_exit=False)
    clock = [10.0]
    signals = StudentNotificationSignals(
        provider.get_meter("test"), expected=True, clock=lambda: clock[0]
    )
    options = CallbackOptions()
    try:
        assert signals.available(options)[0].value == 0
        signals.started()
        assert signals.available(options)[0].value == 0
        assert signals.cycle_age(options) == ()
        signals.cycle(True)
        assert signals.available(options)[0].value == 1
        signals.cycle(False)
        assert signals.available(options)[0].value == 0
        signals.cycle(True)
        clock[0] += STALE_AGE
        assert signals.available(options)[0].value == 0
        assert signals.cycle_age(options)[0].value == STALE_AGE
        signals.stopped()
        assert signals.available(options)[0].value == 0
        signals.close()
        assert signals.expected(options) == ()
        assert signals.available(options) == ()
    finally:
        signals.close()
        provider.shutdown()


async def test_real_sdk_collection_has_only_finite_metadata_and_never_calls_reader() -> None:
    exporter = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[exporter], shutdown_on_exit=False)
    signals = StudentNotificationSignals(provider.get_meter("test"), expected=True)
    reader = Reader()
    try:
        assert await signals.sample(reader)
        signals.started()
        signals.cycle(True)
        data = exporter.get_metrics_data()
        assert data is not None
        label_keys: set[str] = set()
        for resource in data.resource_metrics:
            for scope in resource.scope_metrics:
                for metric in scope.metrics:
                    for point in metric.data.data_points:
                        label_keys.update(point.attributes or {})
                        assert set(point.attributes or {}) <= {
                            "state",
                            "platform",
                            "enabled",
                            "storage",
                        }
        assert label_keys == {"state", "platform", "enabled", "storage"}
        assert reader.calls == 1
        assert len(signals.depth(CallbackOptions())) == len(State)
        assert len(signals.devices(CallbackOptions())) == len(DEVICE_DIMENSIONS)
        assert len(signals.device_attempts(CallbackOptions())) == len(DeviceAttemptState)
    finally:
        signals.close()
        provider.shutdown()


async def test_cancellation_invalidates_cache_and_propagates() -> None:
    entered = asyncio.Event()

    class BlockedReader:
        async def snapshot(self) -> NotificationSnapshot:
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    provider = MeterProvider(shutdown_on_exit=False)
    signals = StudentNotificationSignals(provider.get_meter("test"), expected=True)
    try:
        assert await signals.sample(Reader())
        task = asyncio.create_task(signals.sample(BlockedReader()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert signals.depth(CallbackOptions()) == ()
    finally:
        signals.close()
        provider.shutdown()


async def test_timeout_invalidates_and_pre_stopped_sampler_closes_without_reading() -> None:
    class BlockedReader:
        async def snapshot(self) -> NotificationSnapshot:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    provider = MeterProvider(shutdown_on_exit=False)
    signals = StudentNotificationSignals(provider.get_meter("test"), expected=True)
    reader = Reader()
    try:
        assert not await signals.sample(BlockedReader())
        assert signals.fresh(CallbackOptions())[0].value == 0
        stop = asyncio.Event()
        stop.set()
        await signals.run(reader, stop)
        assert reader.calls == 0
        assert signals.expected(CallbackOptions()) == ()
    finally:
        signals.close()
        provider.shutdown()


def test_decode_uses_database_time_and_rejects_changed_or_private_projection() -> None:
    now = datetime(2026, 11, 14, tzinfo=UTC)
    counts: list[object] = [0] * (len(State) + len(DEVICE_DIMENSIONS) + len(DeviceAttemptState))
    assert decode((*counts, now - timedelta(seconds=DUE_AGE), now)).oldest_due_seconds == DUE_AGE
    assert decode((*counts, None, now)).oldest_due_seconds == 0
    with pytest.raises(ValueError, match="aware source time"):
        decode((*counts, "PRIVATE_ROW_NOT_A_TIMESTAMP", now))
    with pytest.raises(ValueError, match="column count"):
        decode((*counts, None))
    with pytest.raises(ValueError, match="count"):
        decode((-1, *counts[1:], None, now))
    with pytest.raises(ValueError, match="count"):
        decode((True, *counts[1:], None, now))
