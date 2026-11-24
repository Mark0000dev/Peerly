import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.observability.logging import SafeJsonFormatter
from studymate.infrastructure.student_notifications import queue
from studymate.infrastructure.student_notifications.transaction_diagnostics import (
    Cause,
    Operation,
    Phase,
    Progress,
    Stage,
    classify,
    metadata,
)

CANARY = "PRIVATE_SQL_BODY_TOKEN"
POOL_SIZE = 3
DEADLINE_SECONDS = 2


class LockUnavailableError(Exception):
    sqlstate = "55P03"


@pytest.mark.parametrize(
    ("error", "cause"),
    [
        (PoolTimeoutError(CANARY), Cause.POOL),
        (OperationalError(CANARY, {"private": CANARY}, LockUnavailableError(CANARY)), Cause.LOCK),
        (TimeoutError(CANARY), Cause.TIMEOUT),
        (OSError(CANARY), Cause.IO),
    ],
)
def test_suppressed_typed_cause_and_cycles_never_read_private_text(
    error: BaseException, cause: Cause
) -> None:
    outer = StorageUnavailableError(CANARY)
    outer.__context__ = error
    outer.__suppress_context__ = True
    error.__context__ = outer
    assert classify(outer) == cause


@pytest.mark.parametrize("phase", list(Phase))
async def test_stage_and_phase_preserved_on_entry_body_or_commit_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, phase: Phase
) -> None:
    progress = Progress(Operation.AUTHORIZE)
    sessions = async_sessionmaker(expire_on_commit=False)
    failure = StorageUnavailableError(CANARY)
    failure.__context__ = PoolTimeoutError(CANARY)
    seen: list[AsyncSession] = []

    @asynccontextmanager
    async def controlled(
        factory: async_sessionmaker[AsyncSession], *, read_only: bool = False
    ) -> AsyncIterator[AsyncSession]:
        assert factory is sessions
        assert not read_only
        if phase == Phase.ENTRY:
            raise failure
        async with AsyncSession() as session:
            seen.append(session)
            yield session
            assert event.contains(session.sync_session, "after_begin", progress.began)
            if phase == Phase.COMMIT:
                # The driver may have committed before raising. No rollback/absence claim.
                raise failure

    monkeypatch.setattr(queue, "open_transaction", controlled)

    async def work() -> None:
        async with queue.transaction(sessions, progress=progress):
            progress.stage = Stage.ACCOUNTS_LOCK
            if phase == Phase.BODY:
                raise failure

    with pytest.raises(StorageUnavailableError) as caught:
        await work()
    assert caught.value is failure
    diagnostic = caplog.records[-1].__dict__["student_notification_diagnostic"]
    output = metadata(diagnostic)
    assert output["notification_phase"] == phase.value
    assert output["notification_cause"] == Cause.POOL.value
    assert output["notification_deadline_expired"] is False
    if phase == Phase.BODY:
        assert output["notification_stage"] == Stage.ACCOUNTS_LOCK.value
        assert output["notification_caught_before_exit_ms"] is not None
    if phase == Phase.COMMIT:
        assert output["notification_stage"] == Stage.EXIT.value
    for session in seen:
        assert not event.contains(session.sync_session, "after_begin", progress.began)
    rendered = SafeJsonFormatter().format(caplog.records[-1])
    assert CANARY not in rendered
    assert json.loads(rendered)["event"] == "student_notification_transaction_failure"
    assert json.loads(rendered)["notification_phase"] == phase.value


async def test_actual_deadline_cancellation_is_reported_after_cleanup(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    progress = Progress(Operation.AUTHORIZE)
    real_timeout = asyncio.timeout
    sessions = async_sessionmaker(expire_on_commit=False)

    def unit_deadline(seconds: float) -> asyncio.Timeout:
        assert seconds == DEADLINE_SECONDS
        return real_timeout(0.01)

    @asynccontextmanager
    async def controlled(
        factory: async_sessionmaker[AsyncSession], *, read_only: bool = False
    ) -> AsyncIterator[AsyncSession]:
        assert factory is sessions
        assert not read_only
        async with AsyncSession() as session:
            yield session

    monkeypatch.setattr(asyncio, "timeout", unit_deadline)
    monkeypatch.setattr(queue, "open_transaction", controlled)

    async def work() -> None:
        async with queue.transaction(sessions, progress=progress):
            progress.stage = Stage.RELATIONSHIP_LOCK
            await asyncio.Event().wait()

    with pytest.raises(StorageUnavailableError):
        await work()
    output = metadata(caplog.records[-1].__dict__["student_notification_diagnostic"])
    assert output["notification_deadline_expired"] is True
    assert output["notification_stage"] == Stage.RELATIONSHIP_LOCK.value
    assert output["notification_caught_before_exit_ms"] is not None
    assert output["notification_connection_acquired"] is False


async def test_external_task_cancellation_is_not_translated_or_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    entered = asyncio.Event()
    progress = Progress(Operation.AUTHORIZE)
    sessions = async_sessionmaker(expire_on_commit=False)
    seen: list[AsyncSession] = []

    @asynccontextmanager
    async def controlled(
        factory: async_sessionmaker[AsyncSession], *, read_only: bool = False
    ) -> AsyncIterator[AsyncSession]:
        assert factory is sessions
        assert not read_only
        async with AsyncSession() as session:
            seen.append(session)
            yield session

    async def work() -> None:
        async with queue.transaction(sessions, progress=progress):
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(queue, "open_transaction", controlled)
    task = asyncio.create_task(work())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not [r for r in caplog.records if "student_notification_diagnostic" in r.__dict__]
    assert not event.contains(seen[0].sync_session, "after_begin", progress.began)


async def test_pool_snapshot_and_begin_signal_are_numeric_without_connecting() -> None:
    engine = create_async_engine(
        "postgresql+asyncpg://synthetic@127.0.0.1:1/notification_test", pool_size=POOL_SIZE
    )
    progress = Progress(Operation.AUTHORIZE)
    try:
        async with AsyncSession(engine) as session:
            progress.sample_pool(session)
            assert progress.pool_size == POOL_SIZE
            assert progress.pool_checked_out == 0
            assert not progress.connection_acquired
            # Exercise the no-IO after_begin listener's typed fact, not fake PG acceptance.
            progress.began(object(), object(), object())
            assert progress.connection_acquired
    finally:
        await engine.dispose()


def test_formatter_rejects_untyped_or_malformed_metadata() -> None:
    class Private:
        def __str__(self) -> str:
            raise AssertionError("Must not format")

    assert metadata(Private()) == {}
    diagnostic = Progress().diagnostic(TimeoutError(CANARY), deadline_expired=True)
    assert metadata(replace(diagnostic, pool_checked_out=True)) == {}
    assert metadata(replace(diagnostic, observed_after_ms=-1)) == {}
    assert CANARY not in json.dumps(metadata(diagnostic))


MATERIALIZE_STAGES = (
    Stage.CONSUMER_LOCK,
    Stage.GLOBAL_PENDING,
    Stage.SOURCE_EVENTS,
    Stage.CLOCK,
    Stage.SOURCE,
    Stage.MESSAGE_OPERATION,
    Stage.MESSAGE_CONVERSATION,
    Stage.REQUEST_AUTHORITY,
    Stage.RECIPIENT_PENDING,
    Stage.DELIVERY_FLUSH,
)


@pytest.mark.parametrize("stage", MATERIALIZE_STAGES)
async def test_materialize_failure_exports_closed_last_entered_stage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, stage: Stage
) -> None:
    progress = Progress(Operation.MATERIALIZE)
    sessions = async_sessionmaker(expire_on_commit=False)

    @asynccontextmanager
    async def controlled(
        factory: async_sessionmaker[AsyncSession], *, read_only: bool = False
    ) -> AsyncIterator[AsyncSession]:
        assert factory is sessions
        assert not read_only
        async with AsyncSession() as session:
            yield session

    monkeypatch.setattr(queue, "open_transaction", controlled)

    async def work() -> None:
        async with queue.transaction(sessions, progress=progress):
            progress.stage = stage
            raise StorageUnavailableError(CANARY)

    with pytest.raises(StorageUnavailableError):
        await work()
    record = caplog.records[-1]
    output = metadata(record.__dict__["student_notification_diagnostic"])
    assert output["notification_operation"] == "materialize"
    assert output["notification_phase"] == "body"
    assert output["notification_stage"] == stage.value
    assert output["notification_stage_semantics"] == "last_entered"
    assert output["notification_deadline_expired"] is False
    assert output["notification_caught_before_exit_ms"] is not None
    assert CANARY not in SafeJsonFormatter().format(record)
