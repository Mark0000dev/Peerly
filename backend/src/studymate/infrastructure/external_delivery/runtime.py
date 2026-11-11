"""One sequential worker; main lifespan owns task/stop/client/engine resources."""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from studymate.application.errors import StorageUnavailableError
from studymate.application.external_delivery.routing import MaterializeDeliverySources
from studymate.application.external_delivery.worker import DeliverNextExternalEvent

IDLE_SECONDS = 1


class DeliveryWorkerHealth(Protocol):
    def storage_available(self, available: bool) -> None:
        """Finite metric state only; no app technical-alert producer or exception text."""
        ...


@dataclass(frozen=True, slots=True)
class ExternalDeliveryWorker:
    materialize: MaterializeDeliverySources
    deliver: DeliverNextExternalEvent
    health: DeliveryWorkerHealth

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                materialized = await self.materialize()
                if stop.is_set():
                    return
                delivered = await self.deliver()
            except StorageUnavailableError:
                self.health.storage_available(False)
                await idle(stop)
            else:
                self.health.storage_available(True)
                if not materialized and not delivered:
                    await idle(stop)


async def idle(stop: asyncio.Event) -> None:
    try:
        async with asyncio.timeout(IDLE_SECONDS):
            await stop.wait()
    except TimeoutError:
        return
