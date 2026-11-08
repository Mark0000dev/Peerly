"""Standalone SMTP delivery worker; no default or fake provider."""

import asyncio
import signal

from studymate.bootstrap import run_email_worker
from studymate.config import EmailWorkerSettings
from studymate.infrastructure.observability.logging import configure_logging


async def run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for value in signals:
        loop.add_signal_handler(value, stop.set)
    try:
        await run_email_worker(EmailWorkerSettings(), stop)
    finally:
        for value in signals:
            loop.remove_signal_handler(value)


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
