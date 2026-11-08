import asyncio

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.requests.expiry import MAX_EXPIRY_BATCH
from studymate.domain.requests.states import ConnectionRequest
from studymate.infrastructure.requests.expiry_loop import run_expiry_loop
from tests.unit.requests.test_states import request

EXPECTED_BATCHES = 2


async def test_stop_before_start_performs_no_work() -> None:
    stop = asyncio.Event()
    stop.set()

    async def forbidden() -> tuple[ConnectionRequest, ...]:
        raise AssertionError("Stopped worker must not invoke a step")

    await run_expiry_loop(forbidden, stop)


@pytest.mark.parametrize("outage", [False, True])
async def test_idle_and_storage_outage_are_not_busy_loops_and_stop_interrupts_wait(
    outage: bool,
) -> None:
    stop, called = asyncio.Event(), asyncio.Event()
    calls = 0

    async def step() -> tuple[ConnectionRequest, ...]:
        nonlocal calls
        calls += 1
        called.set()
        if outage:
            raise StorageUnavailableError
        return ()

    worker = asyncio.create_task(run_expiry_loop(step, stop))
    try:
        await asyncio.wait_for(called.wait(), timeout=1)
        await asyncio.sleep(0.02)
        assert calls == 1
        stop.set()
        await asyncio.wait_for(worker, timeout=0.5)
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


async def test_nonempty_batches_are_serial_and_stop_prevents_replacement() -> None:
    stop = asyncio.Event()
    active = 0
    calls = 0

    async def step() -> tuple[ConnectionRequest, ...]:
        nonlocal active, calls
        active += 1
        assert active == 1
        await asyncio.sleep(0)
        calls += 1
        active -= 1
        if calls == EXPECTED_BATCHES:
            stop.set()
        return (request(),)

    await run_expiry_loop(step, stop)
    assert calls == EXPECTED_BATCHES
    assert active == 0


@pytest.mark.parametrize("external_cancel", [False, True])
async def test_stop_or_parent_cancellation_awaits_inflight_cleanup(external_cancel: bool) -> None:
    stop, started, cleaned = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def step() -> tuple[ConnectionRequest, ...]:
        started.set()
        try:
            await asyncio.Future[None]()
        finally:
            await asyncio.sleep(0)
            cleaned.set()
        return ()

    worker = asyncio.create_task(run_expiry_loop(step, stop))
    await asyncio.wait_for(started.wait(), timeout=1)
    if external_cancel:
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
    else:
        stop.set()
        await asyncio.wait_for(worker, timeout=0.5)
    assert cleaned.is_set()


@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_unexpected_failure_and_step_cancellation_propagate(
    error: type[BaseException],
) -> None:
    async def step() -> tuple[ConnectionRequest, ...]:
        raise error

    with pytest.raises(error):
        await run_expiry_loop(step, asyncio.Event())


async def test_unbounded_step_result_fails_instead_of_scheduling_more_work() -> None:
    async def step() -> tuple[ConnectionRequest, ...]:
        return (request(),) * (MAX_EXPIRY_BATCH + 1)

    with pytest.raises(RuntimeError, match="bounded batch"):
        await run_expiry_loop(step, asyncio.Event())


@pytest.mark.parametrize(("outage", "expected_delay"), [(False, 1.0), (True, 5.0)])
async def test_fixed_backoff_expires_then_retries_once(outage: bool, expected_delay: float) -> None:
    stop = asyncio.Event()
    calls = 0

    async def step() -> tuple[ConnectionRequest, ...]:
        nonlocal calls
        calls += 1
        if calls == EXPECTED_BATCHES:
            stop.set()
        elif outage:
            raise StorageUnavailableError
        return ()

    started = asyncio.get_running_loop().time()
    await asyncio.wait_for(run_expiry_loop(step, stop), timeout=expected_delay + 2)
    assert asyncio.get_running_loop().time() - started >= expected_delay
    assert calls == EXPECTED_BATCHES


async def test_inflight_cleanup_failure_is_not_swallowed_on_stop() -> None:
    stop, started = asyncio.Event(), asyncio.Event()

    async def step() -> tuple[ConnectionRequest, ...]:
        started.set()
        try:
            await asyncio.Future[None]()
        finally:
            raise RuntimeError("Unexpected expiry cleanup failure")

    worker = asyncio.create_task(run_expiry_loop(step, stop))
    await asyncio.wait_for(started.wait(), timeout=1)
    stop.set()
    with pytest.raises(RuntimeError, match="cleanup failure"):
        await worker
