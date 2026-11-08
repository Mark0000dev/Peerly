import asyncio
from typing import NoReturn

import pytest

from studymate.application.chat_images.worker import ChatImageProcessingStep
from studymate.application.errors import StorageUnavailableError
from studymate.application.media.cleanup import TransportCleanupStep
from studymate.application.media.worker import PhotoProcessingStep
from studymate.infrastructure.workers import media_loop


async def idle_chat_image() -> ChatImageProcessingStep:
    return ChatImageProcessingStep.IDLE


async def idle_chat_cleanup() -> TransportCleanupStep:
    return TransportCleanupStep.IDLE


async def test_media_loop_runs_cleanup_after_work_without_starving_either() -> None:
    stop = asyncio.Event()
    calls: list[str] = []

    async def photo() -> PhotoProcessingStep:
        calls.append("photo")
        return PhotoProcessingStep.READY

    async def cleanup() -> TransportCleanupStep:
        calls.append("cleanup")
        stop.set()
        return TransportCleanupStep.CLEANED

    await media_loop.run_media_loop(photo, idle_chat_image, cleanup, idle_chat_cleanup, stop)
    assert calls == ["photo", "cleanup"]


async def test_media_loop_stop_cancels_inflight_io_and_releases_task() -> None:
    stop, started, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def photo() -> PhotoProcessingStep:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return PhotoProcessingStep.IDLE

    async def cleanup() -> TransportCleanupStep:
        raise AssertionError("Cleanup must not start after stop")

    task = asyncio.create_task(
        media_loop.run_media_loop(photo, idle_chat_image, cleanup, idle_chat_cleanup, stop)
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert cancelled.is_set()


async def test_media_loop_stop_during_cleanup_is_recoverable() -> None:
    stop, started = asyncio.Event(), asyncio.Event()

    async def photo() -> PhotoProcessingStep:
        return PhotoProcessingStep.IDLE

    async def cleanup() -> TransportCleanupStep:
        started.set()
        await asyncio.Event().wait()
        return TransportCleanupStep.CLEANED

    task = asyncio.create_task(
        media_loop.run_media_loop(photo, idle_chat_image, cleanup, idle_chat_cleanup, stop)
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    stop.set()
    await asyncio.wait_for(task, timeout=1)


@pytest.mark.parametrize("result", [PhotoProcessingStep.IDLE, PhotoProcessingStep.BUSY])
async def test_media_loop_idle_backoff_is_interruptible(
    monkeypatch: pytest.MonkeyPatch, result: PhotoProcessingStep
) -> None:
    stop = asyncio.Event()
    delays: list[float] = []

    async def photo() -> PhotoProcessingStep:
        return result

    async def cleanup() -> TransportCleanupStep:
        return TransportCleanupStep.IDLE

    async def wait_stop(value: asyncio.Event, seconds: float) -> None:
        assert value is stop
        delays.append(seconds)
        stop.set()

    monkeypatch.setattr(media_loop, "_wait_for_stop", wait_stop)
    await media_loop.run_media_loop(photo, idle_chat_image, cleanup, idle_chat_cleanup, stop)
    assert delays == [media_loop.IDLE_POLL_SECONDS]


async def test_media_loop_db_failure_backs_off_but_programming_error_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()

    async def unavailable() -> NoReturn:
        raise StorageUnavailableError

    async def cleanup() -> TransportCleanupStep:
        raise AssertionError("No cleanup after failed claim")

    async def wait_stop(value: asyncio.Event, seconds: float) -> None:
        assert seconds == media_loop.OUTAGE_DELAY_SECONDS
        value.set()

    monkeypatch.setattr(media_loop, "_wait_for_stop", wait_stop)
    await media_loop.run_media_loop(unavailable, idle_chat_image, cleanup, idle_chat_cleanup, stop)
    stop.clear()

    async def broken() -> NoReturn:
        raise RuntimeError("Do not disguise programming errors as success")

    with pytest.raises(RuntimeError, match="programming errors"):
        await media_loop.run_media_loop(broken, idle_chat_image, cleanup, idle_chat_cleanup, stop)


async def test_media_loop_wait_timeout_and_already_stopped() -> None:
    await media_loop._wait_for_stop(asyncio.Event(), 0.001)
    stop = asyncio.Event()
    stop.set()
    await media_loop._wait_for_stop(stop, 10)


async def test_media_loop_services_all_four_workloads_sequentially_without_idle_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()
    calls: list[str] = []
    expected = ["photo", "image", "photo_cleanup", "image_cleanup"] * 2

    async def photo() -> PhotoProcessingStep:
        calls.append("photo")
        return PhotoProcessingStep.READY

    async def image() -> ChatImageProcessingStep:
        calls.append("image")
        return ChatImageProcessingStep.READY

    async def cleanup() -> TransportCleanupStep:
        calls.append("photo_cleanup")
        return TransportCleanupStep.CLEANED

    async def image_cleanup() -> TransportCleanupStep:
        calls.append("image_cleanup")
        if len(calls) == len(expected):
            stop.set()
        return TransportCleanupStep.CLEANED

    async def unexpected_backoff(_stop: asyncio.Event, _delay: float) -> NoReturn:
        raise AssertionError("Useful work must not enter idle backoff")

    monkeypatch.setattr(media_loop, "_wait_for_stop", unexpected_backoff)
    await media_loop.run_media_loop(photo, image, cleanup, image_cleanup, stop)
    assert calls == expected


@pytest.mark.parametrize("stage", ["image", "image_cleanup"])
async def test_media_loop_stop_cancels_chat_work_and_does_not_start_next_stage(stage: str) -> None:
    stop, started, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def pause() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def photo() -> PhotoProcessingStep:
        calls.append("photo")
        return PhotoProcessingStep.IDLE

    async def image() -> ChatImageProcessingStep:
        calls.append("image")
        if stage == "image":
            await pause()
        return ChatImageProcessingStep.IDLE

    async def cleanup() -> TransportCleanupStep:
        calls.append("photo_cleanup")
        return TransportCleanupStep.IDLE

    async def image_cleanup() -> TransportCleanupStep:
        calls.append("image_cleanup")
        await pause()
        return TransportCleanupStep.IDLE

    task = asyncio.create_task(
        media_loop.run_media_loop(photo, image, cleanup, image_cleanup, stop)
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert cancelled.is_set()
    assert calls == (
        ["photo", "image"]
        if stage == "image"
        else ["photo", "image", "photo_cleanup", "image_cleanup"]
    )
