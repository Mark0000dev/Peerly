"""Exact cached queue observations; unknown, routing backlog and closure stay honest."""

import asyncio
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import pytest
from opentelemetry.metrics import CallbackOptions
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from studymate.application.errors import StorageUnavailableError
from studymate.domain.external_delivery.delivery import FailureCode
from studymate.domain.external_delivery.sources import Sink
from studymate.infrastructure.observability.delivery_queue import (
    DeliveryQueueSignals,
    DeliveryQueueSnapshot,
    SinkQueueSnapshot,
    decode,
)

STALE_SECONDS = 16
SYNTHETIC_SOURCE_AGE = 40


def snapshot(*, empty: bool = False) -> DeliveryQueueSnapshot:
    return DeliveryQueueSnapshot(
        tuple(
            SinkQueueSnapshot(
                sink, 0 if empty else 2, 0, 0, 0.0, None if empty else FailureCode.CREDENTIALS
            )
            for sink in Sink
        ),
        1,
        float(SYNTHETIC_SOURCE_AGE),
    )


@dataclass(slots=True)
class Reader:
    value: DeliveryQueueSnapshot = field(default_factory=snapshot)
    available: bool = True
    calls: int = 0

    async def snapshot(self) -> DeliveryQueueSnapshot:
        self.calls += 1
        if not self.available:
            raise StorageUnavailableError
        return self.value


async def test_unknown_stale_failed_and_recovered_cache_never_fabricate_empty_queue() -> None:
    provider = MeterProvider(shutdown_on_exit=False)
    clock = [100.0]
    reader = Reader()
    signals = DeliveryQueueSignals(provider.get_meter("synthetic"), clock=lambda: clock[0])
    options = CallbackOptions()
    callbacks = (
        signals.depth,
        signals.oldest,
        signals.blocked,
        signals.sources_pending,
        signals.sources_oldest,
    )
    try:
        for callback in callbacks:
            assert callback(options) == ()
        assert signals.sample_age(options) == ()
        assert signals.fresh(options)[0].value == 0
        assert await signals.sample(reader)
        assert signals.fresh(options)[0].value == 1
        assert signals.depth(options)[0].value > 0
        clock[0] += 1
        reader.available = False
        assert not await signals.sample(reader)
        assert signals.fresh(options)[0].value == 0
        assert signals.sample_age(options)[0].value == 1
        for callback in callbacks:
            assert callback(options) == ()
        reader.available = True
        assert await signals.sample(reader)
        assert signals.fresh(options)[0].value == 1
        clock[0] += STALE_SECONDS
        reader.available = False
        assert not await signals.sample(reader)
        assert signals.fresh(options)[0].value == 0
        assert signals.sample_age(options)[0].value == STALE_SECONDS
        for callback in callbacks:
            assert callback(options) == ()
        reader.available = True
        reader.value = snapshot(empty=True)
        assert await signals.sample(reader)
        assert all(item.value == 0 for item in signals.depth(options))
        assert signals.sources_pending(options)[0].value == 1
        assert signals.sources_oldest(options)[0].value == SYNTHETIC_SOURCE_AGE
        clock[0] -= 1
        assert signals.fresh(options)[0].value == 0
    finally:
        provider.shutdown()


async def test_fixed_block_reason_series_clear_and_sdk_callbacks_never_call_reader() -> None:
    collector = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[collector], shutdown_on_exit=False)
    reader = Reader()
    signals = DeliveryQueueSignals(provider.get_meter("synthetic"))
    options = CallbackOptions()
    try:
        assert await signals.sample(reader)
        blocked = signals.blocked(options)
        assert len(blocked) == len(Sink) * len(FailureCode)
        assert sum(item.value for item in blocked) == len(Sink)
        reader.value = snapshot(empty=True)
        assert await signals.sample(reader)
        assert all(item.value == 0 for item in signals.blocked(options))
        calls = reader.calls
        data = await asyncio.to_thread(collector.get_metrics_data)
        assert data is not None
        assert reader.calls == calls
        for resource in data.resource_metrics:
            for scope in resource.scope_metrics:
                for metric in scope.metrics:
                    for point in metric.data.data_points:
                        assert point.attributes is not None
                        assert set(point.attributes) <= {"sink", "state", "reason"}
        signals.close()
        for callback in (
            signals.depth,
            signals.oldest,
            signals.blocked,
            signals.sources_pending,
            signals.sources_oldest,
            signals.fresh,
            signals.sample_age,
        ):
            assert callback(options) == ()
        assert not await signals.sample(reader)
        assert reader.calls == calls
    finally:
        provider.shutdown()


async def test_sample_timeout_cleans_up_and_cancellation_is_not_swallowed() -> None:
    entered, cleaned = asyncio.Event(), asyncio.Event()

    class BlockedReader:
        async def snapshot(self) -> DeliveryQueueSnapshot:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
            raise AssertionError("Unreachable")

    provider = MeterProvider(shutdown_on_exit=False)
    signals = DeliveryQueueSignals(provider.get_meter("synthetic"))
    try:
        assert not await asyncio.wait_for(signals.sample(BlockedReader()), timeout=1)
        assert cleaned.is_set()
        assert signals.fresh(CallbackOptions())[0].value == 0
        entered.clear()
        task = asyncio.create_task(signals.sample(BlockedReader()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        provider.shutdown()


async def test_run_stops_without_waiting_next_interval_and_disables_callbacks() -> None:
    stop = asyncio.Event()

    class Once:
        async def snapshot(self) -> DeliveryQueueSnapshot:
            stop.set()
            return snapshot()

    provider = MeterProvider(shutdown_on_exit=False)
    signals = DeliveryQueueSignals(provider.get_meter("synthetic"))
    try:
        await asyncio.wait_for(signals.run(Once(), stop), timeout=1)
        assert signals.fresh(CallbackOptions()) == ()
    finally:
        provider.shutdown()


def test_atomic_decoder_requires_both_sinks_exact_counts_and_actual_database_time() -> None:
    at = datetime.now(UTC)
    rows: tuple[tuple[object, ...], ...] = tuple(
        (sink.value, 1, 2, 3, at - timedelta(seconds=5), None, at, 4, at - timedelta(seconds=10))
        for sink in Sink
    )
    result = decode(rows)
    assert len(result.sinks) == len(Sink)
    assert result.sources_pending > 0
    for invalid in (
        (),
        rows[:1],
        (rows[0], rows[0]),
        (rows[0][:-1], rows[1]),
        ((rows[0][0], True, *rows[0][2:]), rows[1]),
        ((*rows[0][:6], at.replace(tzinfo=None), *rows[0][7:]), rows[1]),
    ):
        with pytest.raises(ValueError, match=r"observation|projection|count|time"):
            decode(invalid)
    with pytest.raises(ValueError, match="both seeded"):
        replace(result, sinks=result.sinks[:1])
