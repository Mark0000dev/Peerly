import asyncio
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from studymate.application.media.storage import MediaStorage, MediaStorageUnavailableError
from studymate.domain.media import MediaObjectKind, MediaObjectRef

RETRY_BASE_SECONDS = 30
RETRY_MAX_SECONDS = 3600
RETRY_EXPONENT_CAP = 7


@dataclass(frozen=True, slots=True)
class TransportCleanupLease:
    upload_id: UUID
    generation: UUID
    attempts: int


class TransportCleanupStep(StrEnum):
    IDLE = "idle"
    CLEANED = "cleaned"
    RETRY = "retry"
    STALE = "stale"


class TransportCleanupTransaction(Protocol):
    async def now(self) -> datetime: ...

    async def claim(self, at: datetime, lease_until: datetime) -> TransportCleanupLease | None: ...

    async def finish(
        self, lease: TransportCleanupLease, at: datetime, retry_at: datetime | None
    ) -> bool: ...


class TransportCleanupUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[TransportCleanupTransaction]: ...


@dataclass(frozen=True, slots=True)
class CleanupPolicy:
    lease_duration: timedelta = timedelta(seconds=60)
    provider_timeout: timedelta = timedelta(seconds=20)

    def __post_init__(self) -> None:
        if not timedelta() < self.provider_timeout < self.lease_duration:
            raise ValueError("Cleanup timeout must be positive and shorter than its lease")


@dataclass(frozen=True, slots=True)
class CleanupMediaTransport:
    unit_of_work: TransportCleanupUnitOfWork
    storage: MediaStorage
    policy: CleanupPolicy = CleanupPolicy()

    async def __call__(self) -> TransportCleanupStep:
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            lease = await transaction.claim(now, now + self.policy.lease_duration)
        if lease is None:
            return TransportCleanupStep.IDLE
        failed = False
        try:
            async with asyncio.timeout(self.policy.provider_timeout.total_seconds()):
                await self.storage.remove_transport(
                    MediaObjectRef(lease.upload_id, MediaObjectKind.UPLOAD)
                )
        except (MediaStorageUnavailableError, TimeoutError):
            failed = True
        async with self.unit_of_work.transaction() as transaction:
            now = await transaction.now()
            retry_at = None
            if failed:
                delay = min(
                    RETRY_MAX_SECONDS,
                    RETRY_BASE_SECONDS * 2 ** min(lease.attempts - 1, RETRY_EXPONENT_CAP),
                )
                retry_at = now + timedelta(seconds=delay)
            if not await transaction.finish(lease, now, retry_at):
                return TransportCleanupStep.STALE
        return TransportCleanupStep.RETRY if failed else TransportCleanupStep.CLEANED
