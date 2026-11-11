import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import pytest

from studymate.application.identity.email_delivery import (
    DeliverVerificationEmail,
    DeliveryEnvelopeError,
    DeliveryPolicy,
    DeliveryResolution,
    DeliveryStatus,
    DeliveryStep,
    EmailLease,
    EmailWorkerTransaction,
    PermanentEmailError,
    TransientEmailError,
    VerificationEmail,
)
from studymate.application.identity.email_verification import VerificationCode
from studymate.domain.identity import StudentEmail

MAX_ATTEMPTS = 3
NOW = datetime(2026, 11, 7, tzinfo=UTC)
LEASE = EmailLease(UUID(int=1), UUID(int=2), 1, 1, b"encrypted-envelope")
MESSAGE = VerificationEmail(StudentEmail("tp@mail.apu.edu.my"), VerificationCode("123456"))


class WorkerStore:
    def __init__(self, lease: EmailLease | None = LEASE) -> None:
        self.lease = lease
        self.current = True
        self.accept_ack = True
        self.active_transactions = 0
        self.resolutions: list[DeliveryResolution] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[EmailWorkerTransaction]:
        self.active_transactions += 1
        try:
            yield self
        finally:
            self.active_transactions -= 1

    async def now(self) -> datetime:
        return NOW

    async def cleanup(self, at: datetime, batch: int) -> None:
        assert at == NOW
        assert batch > 0

    async def claim(self, at: datetime, lease_until: datetime) -> EmailLease | None:
        assert lease_until > at
        result, self.lease = self.lease, None
        return result

    async def is_current(self, lease: EmailLease, at: datetime) -> bool:
        assert lease.id == LEASE.id
        assert at == NOW
        return self.current

    async def finish(self, lease: EmailLease, resolution: DeliveryResolution, at: datetime) -> bool:
        assert lease.id == LEASE.id
        assert at == NOW
        self.resolutions.append(resolution)
        return self.accept_ack


class Cipher:
    def __init__(self, *, invalid: bool = False) -> None:
        self.invalid = invalid

    async def open_delivery(self, challenge_id: UUID, payload: bytes) -> VerificationEmail:
        assert challenge_id == LEASE.challenge_id
        assert payload == LEASE.sealed_envelope
        if self.invalid:
            raise DeliveryEnvelopeError
        return MESSAGE


class Sender:
    def __init__(self, store: WorkerStore) -> None:
        self.store = store
        self.failure: Literal["transient", "permanent", "wait"] | None = None
        self.started = asyncio.Event()
        self.sent: list[UUID] = []

    async def send(self, message: VerificationEmail, delivery_id: UUID) -> None:
        assert self.store.active_transactions == 0
        assert message == MESSAGE
        self.started.set()
        self.sent.append(delivery_id)
        if self.failure == "transient":
            raise TransientEmailError
        if self.failure == "permanent":
            raise PermanentEmailError
        if self.failure == "wait":
            await asyncio.Event().wait()


async def test_worker_delivers_outside_transaction_and_acknowledges() -> None:
    store = WorkerStore()
    sender = Sender(store)
    result = await DeliverVerificationEmail(store, sender, Cipher())()
    assert result == DeliveryStep.DELIVERED
    assert sender.sent == [LEASE.id]
    assert store.resolutions == [DeliveryResolution(DeliveryStatus.DELIVERED)]
    assert await DeliverVerificationEmail(store, sender, Cipher())() == DeliveryStep.IDLE


@pytest.mark.parametrize("attempts", [1, 2, 3])
async def test_transient_failure_retries_with_deadline_then_stops(attempts: int) -> None:
    store = WorkerStore(replace(LEASE, attempts=attempts))
    sender = Sender(store)
    sender.failure = "transient"
    result = await DeliverVerificationEmail(store, sender, Cipher())()
    assert result == (DeliveryStep.FAILED if attempts == MAX_ATTEMPTS else DeliveryStep.RETRY)
    assert store.resolutions[0].error == "provider_unavailable"
    if result == DeliveryStep.RETRY:
        assert store.resolutions[0].retry_at is not None
        assert store.resolutions[0].retry_at > NOW


async def test_permanent_and_invalid_envelope_fail_without_retry() -> None:
    store = WorkerStore()
    sender = Sender(store)
    sender.failure = "permanent"
    assert await DeliverVerificationEmail(store, sender, Cipher())() == DeliveryStep.FAILED
    assert store.resolutions[0].error == "provider_rejected"
    store = WorkerStore()
    sender = Sender(store)
    assert (
        await DeliverVerificationEmail(store, sender, Cipher(invalid=True))() == DeliveryStep.FAILED
    )
    assert store.resolutions[0].error == "envelope_invalid"
    assert sender.sent == []


async def test_provider_timeout_is_bounded_and_retryable() -> None:
    store = WorkerStore()
    sender = Sender(store)
    sender.failure = "wait"
    policy = DeliveryPolicy(provider_timeout=timedelta(milliseconds=10))
    assert await DeliverVerificationEmail(store, sender, Cipher(), policy)() == DeliveryStep.RETRY


@pytest.mark.parametrize("accept_ack", [True, False])
async def test_stale_or_cancelled_lease_never_calls_sender(accept_ack: bool) -> None:
    store = WorkerStore()
    store.current = False
    store.accept_ack = accept_ack
    sender = Sender(store)
    assert await DeliverVerificationEmail(store, sender, Cipher())() == (
        DeliveryStep.SKIPPED if accept_ack else DeliveryStep.STALE
    )
    assert sender.sent == []


async def test_lost_lease_cannot_be_reported_delivered() -> None:
    store = WorkerStore()
    store.accept_ack = False
    assert await DeliverVerificationEmail(store, Sender(store), Cipher())() == DeliveryStep.STALE


async def test_cancellation_propagates_and_leaves_lease_for_recovery() -> None:
    store = WorkerStore()
    sender = Sender(store)
    sender.failure = "wait"
    task = asyncio.create_task(DeliverVerificationEmail(store, sender, Cipher())())
    await asyncio.wait_for(sender.started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.resolutions == []
    assert store.active_transactions == 0


@pytest.mark.parametrize("timeout", [timedelta(), timedelta(seconds=31)])
def test_provider_timeout_cannot_outlive_lease(timeout: timedelta) -> None:
    with pytest.raises(ValueError, match="shorter than the lease"):
        DeliveryPolicy(provider_timeout=timeout)


@pytest.mark.parametrize("delays", [(), (timedelta(seconds=-1), timedelta(seconds=1))])
def test_retry_policy_is_bounded(delays: tuple[timedelta, ...]) -> None:
    with pytest.raises(ValueError, match="positive and bounded"):
        DeliveryPolicy(retry_delays=delays)
