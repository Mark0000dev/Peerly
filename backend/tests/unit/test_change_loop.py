import asyncio

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.changes.loop import ChangeMaintenance, run_change_loop


@pytest.mark.parametrize("kind", tuple(ChangeMaintenance))
async def test_stopped_maintenance_never_starts_a_database_step(kind: ChangeMaintenance) -> None:
    stop = asyncio.Event()
    stop.set()

    async def step() -> int:
        raise AssertionError("Stopped maintenance acquired work")

    await run_change_loop(step, stop, kind)


@pytest.mark.parametrize("kind", tuple(ChangeMaintenance))
async def test_stop_cancels_and_awaits_inflight_transaction(kind: ChangeMaintenance) -> None:
    stop = asyncio.Event()
    entered = asyncio.Event()
    released = asyncio.Event()
    never = asyncio.Event()

    async def step() -> int:
        try:
            entered.set()
            await never.wait()
            return 0
        finally:
            released.set()

    task = asyncio.create_task(run_change_loop(step, stop, kind))
    async with asyncio.timeout(1):
        await entered.wait()
        stop.set()
        await task
    assert released.is_set()


@pytest.mark.parametrize("kind", tuple(ChangeMaintenance))
async def test_real_work_drains_without_idle_delay(kind: ChangeMaintenance) -> None:
    stop = asyncio.Event()
    steps = 0
    expected_steps = 2

    async def step() -> int:
        nonlocal steps
        steps += 1
        if steps == expected_steps:
            stop.set()
        return 1

    async with asyncio.timeout(1):
        await run_change_loop(step, stop, kind)
    assert steps == expected_steps


@pytest.mark.parametrize("failed", [False, True])
async def test_stop_interrupts_idle_or_storage_backoff_without_spinning(failed: bool) -> None:
    stop = asyncio.Event()
    entered = asyncio.Event()
    steps = 0

    async def step() -> int:
        nonlocal steps
        steps += 1
        entered.set()
        if failed:
            raise StorageUnavailableError
        return 0

    task = asyncio.create_task(run_change_loop(step, stop, ChangeMaintenance.PUBLICATION))
    async with asyncio.timeout(1):
        await entered.wait()
        stop.set()
        await task
    assert steps == 1


@pytest.mark.parametrize("value", [-1, True, 101])
async def test_invalid_publication_counts_fail_instead_of_hiding_a_broken_worker(
    value: int,
) -> None:
    async def step() -> int:
        return value

    with pytest.raises(RuntimeError, match="bounded batch"):
        await run_change_loop(step, asyncio.Event(), ChangeMaintenance.PUBLICATION)


async def test_unexpected_failure_is_not_silently_retried() -> None:
    async def step() -> int:
        raise RuntimeError("Controlled invariant failure")

    with pytest.raises(RuntimeError, match="Controlled invariant"):
        await run_change_loop(step, asyncio.Event(), ChangeMaintenance.PUBLICATION)
