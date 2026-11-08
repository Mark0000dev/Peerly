"""One durable delivery step; SQL transactions never span provider calls."""

import asyncio
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from studymate.application.identity.email_verification import VerificationCode
from studymate.domain.identity import StudentEmail

MAX_DELIVERY_ATTEMPTS = 3
CLEANUP_BATCH = 100


class TransientEmailError(Exception):
    pass


class PermanentEmailError(Exception):
    pass


class DeliveryEnvelopeError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class VerificationEmail:
    email: StudentEmail = field(repr=False)
    code: VerificationCode = field(repr=False)


@dataclass(frozen=True, slots=True)
class EmailLease:
    id: UUID
    challenge_id: UUID
    generation: int
    attempts: int
    sealed_envelope: bytes = field(repr=False)


class DeliveryStatus(StrEnum):
    DELIVERED = "delivered"
    RETRY = "retry"
    FAILED = "failed"
    CANCELLED = "cancelled"


DeliveryErrorCode = Literal["provider_unavailable", "provider_rejected", "envelope_invalid"]


@dataclass(frozen=True, slots=True)
class DeliveryResolution:
    status: DeliveryStatus
    error: DeliveryErrorCode | None = None
    retry_at: datetime | None = None


class DeliveryStep(StrEnum):
    IDLE = "idle"
    DELIVERED = "delivered"
    RETRY = "retry"
    FAILED = "failed"
    SKIPPED = "skipped"
    STALE = "stale"


class EmailSender(Protocol):
    async def send(self, message: VerificationEmail, delivery_id: UUID) -> None: ...


class DeliveryCipher(Protocol):
    async def open_delivery(self, challenge_id: UUID, payload: bytes) -> VerificationEmail: ...


class EmailWorkerTransaction(Protocol):
    async def now(self) -> datetime: ...

    async def cleanup(self, at: datetime, batch: int) -> None: ...

    async def claim(self, at: datetime, lease_until: datetime) -> EmailLease | None: ...

    async def is_current(self, lease: EmailLease, at: datetime) -> bool: ...

    async def finish(
        self, lease: EmailLease, resolution: DeliveryResolution, at: datetime
    ) -> bool: ...


class EmailWorkerUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[EmailWorkerTransaction]: ...


@dataclass(frozen=True, slots=True)
class DeliveryPolicy:
    lease_duration: timedelta = timedelta(seconds=30)
    provider_timeout: timedelta = timedelta(seconds=5)
    retry_delays: tuple[timedelta, ...] = (timedelta(seconds=1), timedelta(seconds=5))

    def __post_init__(self) -> None:
        if not timedelta() < self.provider_timeout < self.lease_duration:
            raise ValueError("Provider timeout must be positive and shorter than the lease")
        if len(self.retry_delays) != MAX_DELIVERY_ATTEMPTS - 1 or any(
            delay <= timedelta() for delay in self.retry_delays
        ):
            raise ValueError("Delivery retries must be positive and bounded")


@dataclass(frozen=True, slots=True)
class DeliverVerificationEmail:
    unit_of_work: EmailWorkerUnitOfWork
    sender: EmailSender
    cipher: DeliveryCipher
    policy: DeliveryPolicy = DeliveryPolicy()

    async def __call__(self) -> DeliveryStep:
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            await transaction.cleanup(now, CLEANUP_BATCH)
            lease = await transaction.claim(now, now + self.policy.lease_duration)
        if lease is None:
            return DeliveryStep.IDLE
        async with self.unit_of_work.transaction() as transaction:
            current = await transaction.is_current(lease, await transaction.now())
            if not current:
                updated = await transaction.finish(
                    lease, DeliveryResolution(DeliveryStatus.CANCELLED), await transaction.now()
                )
                return DeliveryStep.SKIPPED if updated else DeliveryStep.STALE
        failure: DeliveryErrorCode | None = None
        try:
            message = await self.cipher.open_delivery(lease.challenge_id, lease.sealed_envelope)
            async with asyncio.timeout(self.policy.provider_timeout.total_seconds()):
                await self.sender.send(message, lease.id)
        except (TimeoutError, TransientEmailError):
            failure = "provider_unavailable"
        except PermanentEmailError:
            failure = "provider_rejected"
        except DeliveryEnvelopeError:
            failure = "envelope_invalid"
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            resolution = self._resolution(lease, failure, now)
            updated = await transaction.finish(lease, resolution, now)
        if not updated:
            return DeliveryStep.STALE
        return DeliveryStep(resolution.status.value)

    def _resolution(
        self, lease: EmailLease, failure: DeliveryErrorCode | None, now: datetime
    ) -> DeliveryResolution:
        if failure is None:
            return DeliveryResolution(DeliveryStatus.DELIVERED)
        if failure != "provider_unavailable" or lease.attempts >= MAX_DELIVERY_ATTEMPTS:
            return DeliveryResolution(DeliveryStatus.FAILED, failure)
        return DeliveryResolution(
            DeliveryStatus.RETRY, failure, now + self.policy.retry_delays[lease.attempts - 1]
        )
