"""Actual worker boundary observations: activation, outage, cancellation and teardown."""

import asyncio
from dataclasses import dataclass, field

import pytest
from opentelemetry.metrics import CallbackOptions
from opentelemetry.sdk.metrics import MeterProvider

from studymate.application.errors import StorageUnavailableError
from studymate.application.student_notifications.worker import (
    ConsumeStudentEvents,
    DeliverNextStudentNotification,
)
from studymate.domain.student_notifications.delivery import Claim, Delivery, Outcome
from studymate.infrastructure.observability.student_notifications import StudentNotificationSignals
from studymate.presentation.student_notifications.worker import RunStudentNotifications


@dataclass(slots=True)
class Observation:
    stop: asyncio.Event
    events: list[str] = field(default_factory=list)

    def started(self) -> None:
        self.events.append("start")

    def activated(self) -> None:
        self.events.append("activated")

    def cycle(self, storage_available: bool) -> None:
        self.events.append("available" if storage_available else "unavailable")
        self.stop.set()

    def stopped(self) -> None:
        self.events.append("stop")


@dataclass(slots=True)
class Consumer:
    unavailable: bool = False
    unactivated: bool = False
    blocked: bool = False
    entered: asyncio.Event = field(default_factory=asyncio.Event)

    async def materialize(self, limit: int = 50) -> int:
        del limit
        self.entered.set()
        if self.unavailable:
            raise StorageUnavailableError
        if self.unactivated:
            raise RuntimeError("Explicit activation required")
        if self.blocked:
            await asyncio.Event().wait()
        return 0


@dataclass(slots=True)
class EmptyQueue:
    unavailable: bool = False
    calls: int = 0

    async def claim(self) -> Claim | None:
        self.calls += 1
        if self.unavailable:
            raise StorageUnavailableError
        return None

    async def authorize(self, _claim: Claim) -> Delivery | None:
        raise AssertionError("No claim exists")

    async def finish(self, _claim: Claim, _outcome: Outcome) -> bool:
        raise AssertionError("No provider submission exists")


class NoProvider:
    async def send(self, _delivery: Delivery) -> Outcome:
        raise AssertionError("Empty queue must not call provider")


@pytest.mark.parametrize("unavailable_at", ["none", "consume", "deliver"])
async def test_completed_cycle_distinguishes_activation_from_storage_health(
    unavailable_at: str,
) -> None:
    stop = asyncio.Event()
    observer = Observation(stop)
    consumer = Consumer(unavailable=unavailable_at == "consume")
    queue = EmptyQueue(unavailable=unavailable_at == "deliver")
    worker = RunStudentNotifications(
        ConsumeStudentEvents(consumer),
        DeliverNextStudentNotification(queue, NoProvider()),
        observer,
    )
    await worker(stop)
    expected = ["start"]
    if unavailable_at != "consume":
        expected.append("activated")
    expected.extend(["available" if unavailable_at == "none" else "unavailable", "stop"])
    assert observer.events == expected
    assert queue.calls == (0 if unavailable_at == "consume" else 1)


async def test_missing_explicit_activation_propagates_without_health_tick() -> None:
    stop = asyncio.Event()
    observer = Observation(stop)
    queue = EmptyQueue()
    worker = RunStudentNotifications(
        ConsumeStudentEvents(Consumer(unactivated=True)),
        DeliverNextStudentNotification(queue, NoProvider()),
        observer,
    )
    with pytest.raises(RuntimeError, match="Explicit activation"):
        await worker(stop)
    assert observer.events == ["start", "stop"]
    assert queue.calls == 0


async def test_cancelled_consume_stops_observation_without_fabricating_cycle() -> None:
    stop = asyncio.Event()
    observer = Observation(stop)
    consumer = Consumer(blocked=True)
    worker = RunStudentNotifications(
        ConsumeStudentEvents(consumer),
        DeliverNextStudentNotification(EmptyQueue(), NoProvider()),
        observer,
    )
    task = asyncio.create_task(worker(stop))
    await consumer.entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert observer.events == ["start", "stop"]


async def test_pre_stopped_worker_does_not_claim_start_or_activation() -> None:
    stop = asyncio.Event()
    stop.set()
    observer = Observation(stop)
    consumer = Consumer()
    await RunStudentNotifications(
        ConsumeStudentEvents(consumer),
        DeliverNextStudentNotification(EmptyQueue(), NoProvider()),
        observer,
    )(stop)
    assert observer.events == []
    assert not consumer.entered.is_set()


@pytest.mark.parametrize("eligible", [False, True])
def test_selected_launch_waits_for_real_activation_and_cycle_before_health(eligible: bool) -> None:
    provider = MeterProvider(shutdown_on_exit=False)
    signals = StudentNotificationSignals(
        provider.get_meter("test"), expected=False, activation_pending=eligible
    )
    options = CallbackOptions()
    try:
        signals.activated()  # A callback before actual start cannot enable anything.
        assert signals.expected(options)[0].value == 0
        signals.started()
        signals.cycle(True)
        assert signals.expected(options)[0].value == 0
        assert signals.available(options) == ()
        signals.activated()
        assert signals.expected(options)[0].value == int(eligible)
        if eligible:
            assert signals.available(options)[0].value == 0
            signals.cycle(False)
            assert signals.available(options)[0].value == 0
            signals.cycle(True)
            assert signals.available(options)[0].value == 1
        else:
            assert signals.available(options) == ()
        signals.close()
        signals.activated()
        assert signals.expected(options) == ()
        assert signals.available(options) == ()
    finally:
        signals.close()
        provider.shutdown()


def test_outage_transition_logs_are_closed_metadata_without_idle_spam(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import json
    import logging

    from studymate.infrastructure.observability.logging import SafeJsonFormatter

    provider = MeterProvider(shutdown_on_exit=False)
    signals = StudentNotificationSignals(provider.get_meter("test"), expected=True)
    caplog.set_level(logging.INFO, logger="studymate.student_notifications")
    try:
        signals.started()
        signals.cycle(False)
        signals.cycle(False)
        signals.cycle(True)
        signals.cycle(False)
        signals.stopped()
        signals.close()
        records = [
            item for item in caplog.records if item.name == "studymate.student_notifications"
        ]
        expected_events = [
            "worker_storage_unavailable",
            "worker_storage_unavailable",
            "worker_stopped",
        ]
        assert len(records) == len(expected_events)
        formatter = SafeJsonFormatter()
        rendered = [json.loads(formatter.format(record)) for record in records]
        assert [item["event"] for item in rendered] == [
            "worker_storage_unavailable",
            "worker_storage_unavailable",
            "worker_stopped",
        ]
        for item in rendered:
            assert item["worker"] == "student_notifications"
            assert set(item) <= {"time", "level", "event", "worker", "outcome"}
        assert rendered[0]["outcome"] == "storage_unavailable"
        assert "outcome" not in rendered[-1]
    finally:
        signals.close()
        provider.shutdown()


async def test_pending_activation_sampler_never_reads_database_before_consume_proof() -> None:
    from studymate.infrastructure.observability.student_notifications import NotificationSnapshot

    class Reader:
        calls = 0

        async def snapshot(self) -> NotificationSnapshot:
            self.calls += 1
            return NotificationSnapshot((0,) * 7, (0,) * 6, (0,) * 5, 0)

    provider = MeterProvider(shutdown_on_exit=False)
    signals = StudentNotificationSignals(
        provider.get_meter("test"), expected=False, activation_pending=True
    )
    reader = Reader()
    try:
        signals.started()
        assert not await signals.sample(reader)
        assert reader.calls == 0
        signals.activated()
        assert await signals.sample(reader)
        assert reader.calls == 1
        assert signals.fresh(CallbackOptions())[0].value == 1
    finally:
        signals.close()
        provider.shutdown()
