"""One bounded provider request outside SQL; the database owns durable leases."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from studymate.domain.external_delivery.delivery import (
    MAX_ATTEMPTS,
    DeliveryLease,
    DeliveryResult,
    DeliveryState,
    DestinationRef,
    FailureCode,
    ResultKind,
)
from studymate.domain.external_delivery.sources import Sink
from studymate.domain.time import require_aware

HTTP_DEADLINE_SECONDS = 5
LEASE_SECONDS = 30
MAX_BACKOFF_SECONDS = 3600
MAX_PROVIDER_RETRY_SECONDS = 7 * 24 * 3600


class DestinationRegistry(Protocol):
    def destination(self, sink: Sink) -> DestinationRef | None:
        "An already registered exact target revision; credentials may rotate independently."
        ...


class ExternalSender(Protocol):
    async def send(self, lease: DeliveryLease) -> DeliveryResult:
        """Sanitized bounded HTTP result; never log URLs/credentials/provider bodies."""
        ...


class DeliveryQueue(Protocol):
    async def next_sink(self, excluded: frozenset[Sink]) -> Sink | None:
        """Persisted fair rotation, not source backlog size or a long SQL transaction."""
        ...

    async def claim(self, destination: DestinationRef, lease_seconds: int) -> DeliveryLease | None:
        "Commit source lease/destination/started attempt BEFORE return; no open SQL context."
        ...

    async def finish(self, lease: DeliveryLease, result: DeliveryResult) -> None:
        "CAS current delivery lease; retain stale attempt outcome without changing a newer lease."
        ...


@dataclass(frozen=True, slots=True)
class DeliveryDisposition:
    state: DeliveryState
    next_attempt_at: datetime
    cooldown_until: datetime | None = None
    block_sink: bool = False


def plan_completion(attempt_no: int, result: DeliveryResult, at: datetime) -> DeliveryDisposition:
    require_aware(at)
    if isinstance(attempt_no, bool) or not 1 <= attempt_no <= MAX_ATTEMPTS:
        raise ValueError("Delivery completion lost its bounded actual attempt")
    if result.kind == ResultKind.ACCEPTED:
        return DeliveryDisposition(DeliveryState.SUCCEEDED, at)
    if result.failure in (FailureCode.CREDENTIALS, FailureCode.DESTINATION):
        return DeliveryDisposition(DeliveryState.DEAD, at, block_sink=True)
    if (
        result.retry_after_seconds is not None
        and result.retry_after_seconds > MAX_PROVIDER_RETRY_SECONDS
    ):
        return DeliveryDisposition(DeliveryState.DEAD, at, block_sink=True)
    delay = result.retry_after_seconds or (
        60
        if result.failure == FailureCode.RATE_LIMITED
        else min(MAX_BACKOFF_SECONDS, 2**attempt_no)
    )
    due = at + timedelta(seconds=delay)
    cooldown = due if result.failure == FailureCode.RATE_LIMITED else None
    state = (
        DeliveryState.DEAD
        if result.kind == ResultKind.PERMANENT or attempt_no >= MAX_ATTEMPTS
        else DeliveryState.RETRY
    )
    return DeliveryDisposition(state, due, cooldown)


@dataclass(frozen=True, slots=True)
class DeliverNextExternalEvent:
    queue: DeliveryQueue
    destinations: DestinationRegistry
    sender: ExternalSender

    async def __call__(self) -> bool:
        # Visit each sink at most once. An unavailable sink never starves another.
        visited: set[Sink] = set()
        for _ in Sink:
            sink = await self.queue.next_sink(frozenset(visited))
            if sink is None:
                break
            if sink in visited:
                raise RuntimeError("Delivery queue repeated an excluded sink")
            visited.add(sink)
            destination = self.destinations.destination(sink)
            if destination is None:
                continue
            if destination.sink != sink:
                raise RuntimeError("External registry returned another sink's destination")
            lease = await self.queue.claim(destination, LEASE_SECONDS)
            if lease is None:
                continue
            if lease.destination != destination:
                raise RuntimeError("External queue rebound an immutable delivery destination")
            try:
                async with asyncio.timeout(HTTP_DEADLINE_SECONDS):
                    result = await self.sender.send(lease)
            except TimeoutError:
                result = DeliveryResult(ResultKind.AMBIGUOUS, FailureCode.TIMEOUT)
            except asyncio.CancelledError:
                # Leave the durable started attempt/lease for honest expiry recovery.
                # Cancellation is never converted into success or a swallowed result.
                raise
            await self.queue.finish(lease, result)
            return True
        return False
