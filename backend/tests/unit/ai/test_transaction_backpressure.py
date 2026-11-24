"""Controlled I/O/cleanup boundaries with real unbound sessions, no SQL doubles.

Identity, durable writes and PostgreSQL locks still need the original PG cases.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.ai.policy import AdmissionPolicy
from studymate.application.ai.ports import AiUnavailableError
from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.ai import persistence
from studymate.infrastructure.ai.persistence import SqlAiUnitOfWork
from studymate.infrastructure.ai.transaction_diagnostics import AiTransactionDiagnostic

POOL_CONNECTIONS = 2
ARRIVALS = 500
RECOVERY_TRANSACTIONS = POOL_CONNECTIONS + 1
PRODUCTION_BUDGET_SECONDS = 2.0


@dataclass(slots=True)
class ControlledBoundary:
    allow_entry: asyncio.Event = field(default_factory=asyncio.Event)
    allow_exit: asyncio.Event = field(default_factory=asyncio.Event)
    two_entered: asyncio.Event = field(default_factory=asyncio.Event)
    closing: asyncio.Event = field(default_factory=asyncio.Event)
    entered: int = 0
    active: int = 0
    maximum: int = 0
    sessions: list[AsyncSession] = field(default_factory=list)

    @asynccontextmanager
    async def transaction(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        self.entered += 1
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        if self.active == POOL_CONNECTIONS:
            self.two_entered.set()
        try:
            await self.allow_entry.wait()
            async with sessions() as session:
                self.sessions.append(session)
                yield session
        finally:
            self.closing.set()
            await self.allow_exit.wait()
            self.active -= 1


async def invoke(uow: SqlAiUnitOfWork, arrived: asyncio.Event | None = None) -> None:
    if arrived is not None:
        arrived.set()
    async with uow.transaction():
        pass


async def test_500_arrivals_wait_before_orm_entry_then_all_run_with_distinct_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boundary = ControlledBoundary()
    boundary.allow_exit.set()
    monkeypatch.setattr(persistence, "open_transaction", boundary.transaction)
    uow = SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False))
    assert uow.policy.request_budget_seconds == PRODUCTION_BUDGET_SECONDS
    all_arrived = asyncio.Event()
    arrivals = 0

    async def request() -> None:
        nonlocal arrivals
        arrivals += 1
        if arrivals == ARRIVALS:
            all_arrived.set()
        await invoke(uow)

    tasks = [asyncio.create_task(request()) for _ in range(ARRIVALS)]
    try:
        async with asyncio.timeout(2):
            await all_arrived.wait()
            await boundary.two_entered.wait()
            # No queue-full shortcut: every arrival subsequently gets its own
            # transaction. Pending arrivals must not create ORM contexts yet.
            assert boundary.entered == POOL_CONNECTIONS
    finally:
        boundary.allow_entry.set()
        await asyncio.gather(*tasks)
    assert arrivals == boundary.entered == len(boundary.sessions) == ARRIVALS
    assert len({id(session) for session in boundary.sessions}) == ARRIVALS
    assert boundary.maximum == POOL_CONNECTIONS
    assert boundary.active == 0


async def test_cancelled_waiter_never_opens_transaction_or_steals_recovery_capacity(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    boundary = ControlledBoundary()
    boundary.allow_exit.set()
    monkeypatch.setattr(persistence, "open_transaction", boundary.transaction)
    uow = SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False))
    holders = [asyncio.create_task(invoke(uow)) for _ in range(POOL_CONNECTIONS)]
    await boundary.two_entered.wait()
    arrived = asyncio.Event()
    waiter = asyncio.create_task(invoke(uow, arrived))
    await arrived.wait()
    try:
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert boundary.entered == POOL_CONNECTIONS
        assert not caplog.records
    finally:
        boundary.allow_entry.set()
        await asyncio.gather(*holders)
    await invoke(uow)
    assert boundary.entered == RECOVERY_TRANSACTIONS
    assert boundary.active == 0


async def test_wait_uses_existing_request_deadline_and_does_not_enter_after_expiry(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    boundary = ControlledBoundary()
    monkeypatch.setattr(persistence, "open_transaction", boundary.transaction)
    # Smaller supported test budget only; production default stays exactly2s.
    uow = SqlAiUnitOfWork(
        async_sessionmaker(expire_on_commit=False), AdmissionPolicy(request_budget_seconds=0.03)
    )
    holders = [asyncio.create_task(invoke(uow)) for _ in range(POOL_CONNECTIONS)]
    await boundary.two_entered.wait()
    try:
        with pytest.raises(AiUnavailableError):
            await invoke(uow)
        assert boundary.entered == POOL_CONNECTIONS
        assert not boundary.sessions
        diagnostic = vars(caplog.records[-1]).get("ai_transaction_diagnostic")
        assert isinstance(diagnostic, AiTransactionDiagnostic)
        assert diagnostic.deadline_expired is True
        assert diagnostic.phase.value == "entry"
        assert diagnostic.cause.value == "request_deadline"
    finally:
        boundary.allow_exit.set()
        results = await asyncio.gather(*holders, return_exceptions=True)
    assert all(isinstance(result, AiUnavailableError) for result in results)
    boundary.allow_entry.set()
    await invoke(uow)
    assert boundary.entered == RECOVERY_TRANSACTIONS
    assert boundary.active == 0


async def test_transaction_exit_keeps_capacity_until_cleanup_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boundary = ControlledBoundary()
    boundary.allow_entry.set()
    monkeypatch.setattr(persistence, "open_transaction", boundary.transaction)
    uow = SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False))
    holders = [asyncio.create_task(invoke(uow)) for _ in range(POOL_CONNECTIONS)]
    await boundary.two_entered.wait()
    await boundary.closing.wait()
    arrived = asyncio.Event()
    waiter = asyncio.create_task(invoke(uow, arrived))
    await arrived.wait()
    try:
        assert boundary.entered == POOL_CONNECTIONS
        assert boundary.active == POOL_CONNECTIONS
    finally:
        boundary.allow_exit.set()
        await asyncio.gather(*holders, waiter)
    assert boundary.entered == RECOVERY_TRANSACTIONS
    assert boundary.active == 0


@pytest.mark.parametrize("storage_failure", [False, True])
async def test_body_failure_or_cancellation_releases_capacity_only_after_exit(
    monkeypatch: pytest.MonkeyPatch, storage_failure: bool
) -> None:
    boundary = ControlledBoundary()
    boundary.allow_entry.set()
    monkeypatch.setattr(persistence, "open_transaction", boundary.transaction)
    uow = SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False))

    async def failing() -> None:
        async with uow.transaction():
            if storage_failure:
                raise StorageUnavailableError("synthetic unavailable boundary")
            raise asyncio.CancelledError

    holders = [asyncio.create_task(failing()) for _ in range(POOL_CONNECTIONS)]
    await boundary.two_entered.wait()
    await boundary.closing.wait()
    arrived = asyncio.Event()
    waiter = asyncio.create_task(invoke(uow, arrived))
    await arrived.wait()
    try:
        assert boundary.entered == POOL_CONNECTIONS
    finally:
        boundary.allow_exit.set()
        results = await asyncio.gather(*holders, return_exceptions=True)
        await waiter
    expected = AiUnavailableError if storage_failure else asyncio.CancelledError
    assert all(isinstance(result, expected) for result in results)
    assert boundary.entered == RECOVERY_TRANSACTIONS
    assert boundary.active == 0
