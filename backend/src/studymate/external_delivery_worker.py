"""Explicitly configured two-sink worker; no backfill or automatic credential setup."""

import asyncio
import signal

from studymate.bootstrap import run_external_delivery_worker
from studymate.config import ExternalDeliveryWorkerSettings
from studymate.infrastructure.observability.logging import configure_logging


async def run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for value in signals:
        loop.add_signal_handler(value, stop.set)
    try:
        await run_external_delivery_worker(ExternalDeliveryWorkerSettings(), stop)
    finally:
        for value in signals:
            loop.remove_signal_handler(value)


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
