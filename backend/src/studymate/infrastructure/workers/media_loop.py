import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

from studymate.application.chat_images.worker import ChatImageProcessingStep
from studymate.application.errors import StorageUnavailableError
from studymate.application.media.cleanup import TransportCleanupStep
from studymate.application.media.worker import PhotoProcessingStep

IDLE_POLL_SECONDS = 1
OUTAGE_DELAY_SECONDS = 5


async def _wait_for_stop(stop: asyncio.Event, delay_seconds: float) -> None:
    try:
        async with asyncio.timeout(delay_seconds):
            await stop.wait()
    except TimeoutError:
        return


async def _until_stopped[T](step: Callable[[], Awaitable[T]], stop: asyncio.Event) -> T | None:
    work = asyncio.ensure_future(step())
    stopped = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait((work, stopped), return_when=asyncio.FIRST_COMPLETED)
        if work in done:
            return await work
        return None
    finally:
        work.cancel()
        stopped.cancel()
        try:
            await work
        except asyncio.CancelledError:
            pass
        finally:
            with suppress(asyncio.CancelledError):
                await stopped


async def run_media_loop(
    photo: Callable[[], Awaitable[PhotoProcessingStep]],
    chat_image: Callable[[], Awaitable[ChatImageProcessingStep]],
    cleanup: Callable[[], Awaitable[TransportCleanupStep]],
    chat_cleanup: Callable[[], Awaitable[TransportCleanupStep]],
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            processed = await _until_stopped(photo, stop)
            if processed is None or stop.is_set():
                return
            image = await _until_stopped(chat_image, stop)
            if image is None or stop.is_set():
                return
            cleaned = await _until_stopped(cleanup, stop)
            if cleaned is None or stop.is_set():
                return
            image_cleaned = await _until_stopped(chat_cleanup, stop)
            if image_cleaned is None:
                return
        except StorageUnavailableError:
            await _wait_for_stop(stop, OUTAGE_DELAY_SECONDS)
            continue
        if (
            processed in {PhotoProcessingStep.IDLE, PhotoProcessingStep.BUSY}
            and image in {ChatImageProcessingStep.IDLE, ChatImageProcessingStep.BUSY}
            and cleaned in {TransportCleanupStep.IDLE, TransportCleanupStep.RETRY}
            and image_cleaned in {TransportCleanupStep.IDLE, TransportCleanupStep.RETRY}
        ):
            await _wait_for_stop(stop, IDLE_POLL_SECONDS)
