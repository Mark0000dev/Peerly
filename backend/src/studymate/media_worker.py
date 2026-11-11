"""Standalone private photo worker; explicit S3 credentials, bounded codec, no auth SDK chain."""

import asyncio
import signal

from studymate.bootstrap import run_media_worker
from studymate.config import MediaWorkerSettings
from studymate.infrastructure.observability.logging import configure_logging


async def run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for value in signals:
        loop.add_signal_handler(value, stop.set)
    try:
        await run_media_worker(MediaWorkerSettings(), stop)
    finally:
        for value in signals:
            loop.remove_signal_handler(value)


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
