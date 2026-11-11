import asyncio

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.email_delivery import DeliveryStep
from studymate.infrastructure.workers import email_loop


async def test_worker_stops_before_claiming() -> None:
    stop = asyncio.Event()
    stop.set()

    async def forbidden() -> DeliveryStep:
        raise AssertionError("A stopped worker claimed work")

    await email_loop.run_email_loop(forbidden, stop)


async def test_worker_recovers_from_outage_and_can_stop_during_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()
    calls = 0
    monkeypatch.setattr(email_loop, "OUTAGE_DELAY_SECONDS", 0.001)
    monkeypatch.setattr(email_loop, "IDLE_POLL_SECONDS", 0.001)

    async def step() -> DeliveryStep:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise StorageUnavailableError
        stop.set()
        return DeliveryStep.IDLE

    await asyncio.wait_for(email_loop.run_email_loop(step, stop), timeout=1)
    assert calls > 1


async def test_busy_worker_does_not_wait_before_next_job() -> None:
    stop = asyncio.Event()

    async def step() -> DeliveryStep:
        stop.set()
        return DeliveryStep.DELIVERED

    await email_loop.run_email_loop(step, stop)


async def test_programming_errors_terminate_worker() -> None:
    async def broken() -> DeliveryStep:
        raise RuntimeError("controlled programming error")

    with pytest.raises(RuntimeError, match="programming"):
        await email_loop.run_email_loop(broken, asyncio.Event())
