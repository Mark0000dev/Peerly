"""Explicit notification delivery worker and separate no-backfill activation command."""

import argparse
import asyncio
import signal
from collections.abc import Sequence
from enum import StrEnum

from studymate.bootstrap import activate_student_notifications, run_configured_student_notifications
from studymate.infrastructure.observability.logging import configure_logging
from studymate.infrastructure.student_notifications.settings import (
    StudentNotificationDeliverySettings,
    StudentNotificationWorkerSettings,
)


class Operation(StrEnum):
    RUN = "run"
    ACTIVATE = "activate"


def parse_operation(argv: Sequence[str] | None = None) -> Operation:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("run", help="Start delivery only; never activate source consumption")
    activation = commands.add_parser(
        "activate", help="Owner action: only new source events from now"
    )
    activation.add_argument("--confirm-no-backfill", action="store_true", required=True)
    value: object = parser.parse_args(argv).operation
    if not isinstance(value, str):
        raise RuntimeError("Explicit worker command required")
    return Operation(value)


async def run(operation: Operation) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for value in signals:
        loop.add_signal_handler(value, stop.set)
    try:
        if operation == Operation.ACTIVATE:
            await activate_student_notifications(StudentNotificationWorkerSettings())
        else:
            await run_configured_student_notifications(StudentNotificationDeliverySettings(), stop)
    finally:
        for value in signals:
            loop.remove_signal_handler(value)


def main(argv: Sequence[str] | None = None) -> None:
    operation = parse_operation(argv)
    configure_logging()
    asyncio.run(run(operation))


if __name__ == "__main__":
    main()
