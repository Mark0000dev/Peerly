import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from studymate.domain.student_notifications.delivery import Claim, Delivery, Outcome


class PushDelivery(Protocol):
    async def send(self, delivery: Delivery) -> Outcome:
        """Metadata-only fixed preview; stable delivery.id is provider idempotency key.

        RETRYABLE means definitively not accepted. Ambiguous transport errors MUST
        return UNKNOWN. No device display/exactly-once claim follows ACCEPTED.
        """
        ...


class RecipientQueue(Protocol):
    async def claim(self) -> Claim | None: ...

    async def authorize(self, claim: Claim) -> Delivery | None:
        """Fresh source/actor/relationship/preference check, fence, durable sending commit."""
        ...

    async def finish(self, claim: Claim, outcome: Outcome) -> bool: ...


class SourceConsumer(Protocol):
    async def materialize(self, limit: int = 50) -> int: ...


@dataclass(frozen=True, slots=True)
class ConsumeStudentEvents:
    consumer: SourceConsumer

    async def __call__(self) -> int:
        return await self.consumer.materialize()


@dataclass(frozen=True, slots=True)
class DeliverNextStudentNotification:
    queue: RecipientQueue
    transport: PushDelivery
    timeout: timedelta = timedelta(seconds=3)

    def __post_init__(self) -> None:
        if not timedelta(0) < self.timeout <= timedelta(seconds=3):
            raise ValueError(
                "Delivery transport timeout must be positive and at most three seconds"
            )

    async def __call__(self) -> bool:
        claim = await self.queue.claim()
        if claim is None:
            return False
        delivery = await self.queue.authorize(claim)
        if delivery is None:
            return True
        try:
            async with asyncio.timeout(self.timeout.total_seconds()):
                outcome = await self.transport.send(delivery)
        except TimeoutError:
            outcome = Outcome.UNKNOWN
        except asyncio.CancelledError:
            # If cancellation interrupts this cleanup, durable SENDING still expires to UNKNOWN.
            await self.queue.finish(claim, Outcome.UNKNOWN)
            raise
        await self.queue.finish(claim, outcome)
        return True
