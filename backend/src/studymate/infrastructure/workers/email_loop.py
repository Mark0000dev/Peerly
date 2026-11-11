import asyncio
from collections.abc import Awaitable, Callable

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.email_delivery import DeliveryStep

IDLE_POLL_SECONDS = 1
OUTAGE_DELAY_SECONDS = 5


async def _wait_for_stop(stop: asyncio.Event, delay_seconds: float) -> None:
    try:
        async with asyncio.timeout(delay_seconds):
            await stop.wait()
    except TimeoutError:
        return


async def run_email_loop(step: Callable[[], Awaitable[DeliveryStep]], stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            result = await step()
        except StorageUnavailableError:
            await _wait_for_stop(stop, OUTAGE_DELAY_SECONDS)
            continue
        if result == DeliveryStep.IDLE:
            await _wait_for_stop(stop, IDLE_POLL_SECONDS)
