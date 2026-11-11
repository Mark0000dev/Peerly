from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.chat_images.worker import (
    ChatImageInfo,
    ChatImageLease,
    ChatImageProcessingStep,
)
from studymate.domain.chat_images import ChatImageFailure
from studymate.infrastructure.chat_images.models import (
    ChatImageAttemptRecord,
    ChatImageRecord,
    ChatImageRevisionRecord,
)
from studymate.infrastructure.chat_images.worker import (
    SqlChatImageWorkerTransaction,
    SqlChatImageWorkerUnitOfWork,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from tests.image_fixture import encoded
from tests.integration.test_chat_image_worker import queued

pytestmark = pytest.mark.integration
LEASE_DURATION = timedelta(minutes=2)


async def claim(
    unit: SqlChatImageWorkerUnitOfWork,
) -> ChatImageLease | ChatImageProcessingStep | None:
    async with unit.transaction() as transaction:
        at = await transaction.now()
        return await transaction.claim(at, at + LEASE_DURATION)


async def test_expired_lease_reclaim_fences_the_original_attempt_without_changing_new_generation(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned, image = await queued(identity_engine, encoded())
    unit = SqlChatImageWorkerUnitOfWork(owned.api.sessions)
    first = await claim(unit)
    assert isinstance(first, ChatImageLease)
    async with owned.api.sessions() as session:
        attempt = await session.get(ChatImageAttemptRecord, first.attempt_id)
        assert attempt is not None
        after_lease = attempt.lease_until + timedelta(microseconds=1)

    async def clock(_transaction: SqlChatImageWorkerTransaction) -> datetime:
        return after_lease

    monkeypatch.setattr(SqlChatImageWorkerTransaction, "now", clock)
    second = await claim(unit)
    assert isinstance(second, ChatImageLease)
    assert second.attempts == first.attempts + 1
    assert second.attempt_id != first.attempt_id
    async with unit.transaction() as transaction:
        assert (
            await transaction.complete(first, ChatImageInfo(1, 1, 1, b"d" * 32), after_lease)
            == ChatImageProcessingStep.STALE
        )
    async with owned.api.sessions() as session:
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        assert root.current_version == second.image.version
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.attempt_id == second.attempt_id
        assert current.state == "processing"
        old = await session.get(ChatImageAttemptRecord, first.attempt_id)
        assert old is not None
        assert old.outcome == "interrupted"
        assert old.display_digest == b"d" * 32


async def test_retry_uses_actual_persisted_deadline_and_preserves_ended_attempt(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned, image = await queued(identity_engine, encoded())
    unit = SqlChatImageWorkerUnitOfWork(owned.api.sessions)
    first = await claim(unit)
    assert isinstance(first, ChatImageLease)
    async with unit.transaction() as transaction:
        at = await transaction.now()
        result = await transaction.reject(
            first, ChatImageFailure.STORAGE_UNAVAILABLE, at, at + timedelta(seconds=2)
        )
    assert result == ChatImageProcessingStep.RETRY
    async with owned.api.sessions() as session:
        attempt = await session.get(ChatImageAttemptRecord, first.attempt_id)
        assert attempt is not None
        assert attempt.finished_at is not None
        assert attempt.next_attempt_at is not None
        finished, due = attempt.finished_at, attempt.next_attempt_at
        assert due - finished == timedelta(seconds=2)
    current_time = finished

    async def clock(_transaction: SqlChatImageWorkerTransaction) -> datetime:
        return current_time

    monkeypatch.setattr(SqlChatImageWorkerTransaction, "now", clock)
    assert await claim(unit) is None
    current_time = due
    second = await claim(unit)
    assert isinstance(second, ChatImageLease)
    assert second.attempts == first.attempts + 1
    async with owned.api.sessions() as session:
        attempt = await session.get(ChatImageAttemptRecord, first.attempt_id)
        assert attempt is not None
        assert attempt.outcome == "retry"
        assert attempt.finished_at == finished
        assert attempt.next_attempt_at == due
        assert attempt.failure == "storage_unavailable"
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        assert root.current_version == second.image.version


async def test_three_crashed_attempts_settle_rejected_without_a_fourth_execution(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned, image = await queued(identity_engine, encoded())
    unit = SqlChatImageWorkerUnitOfWork(owned.api.sessions)
    async with unit.transaction() as transaction:
        current_time = await transaction.now()

    async def clock(_transaction: SqlChatImageWorkerTransaction) -> datetime:
        return current_time

    monkeypatch.setattr(SqlChatImageWorkerTransaction, "now", clock)
    for number in range(1, 4):
        lease = await claim(unit)
        assert isinstance(lease, ChatImageLease)
        assert lease.attempts == number
        async with owned.api.sessions() as session:
            attempt = await session.get(ChatImageAttemptRecord, lease.attempt_id)
            assert attempt is not None
            current_time = attempt.lease_until + timedelta(microseconds=1)
    assert await claim(unit) == ChatImageProcessingStep.REJECTED
    async with owned.api.sessions() as session:
        attempts = tuple(await session.scalars(select(ChatImageAttemptRecord)))
        assert tuple(sorted(item.number for item in attempts)) == (1, 2, 3)
        assert all(item.outcome == "interrupted" for item in attempts)
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == "rejected"
        assert current.failure == "processing_unavailable"


@pytest.mark.parametrize(
    "reason",
    [
        "owner_banned",
        "owner_deleted",
        "peer_banned",
        "peer_deleted",
        "owner_unverified",
        "peer_unverified",
    ],
)
async def test_ineligible_current_account_or_contact_never_creates_a_processing_attempt(
    identity_engine: AsyncEngine,
    reason: str,
) -> None:
    owned, image = await queued(identity_engine, encoded())
    target = owned.sender if reason.startswith("owner") else owned.recipient
    async with owned.api.sessions.begin() as session:
        if reason.endswith("unverified"):
            await session.execute(
                update(InstitutionalBindingRecord)
                .where(InstitutionalBindingRecord.account_id == target.id)
                .values(revoked_at=func.clock_timestamp())
            )
        else:
            column = (
                AccountRecord.banned_at if reason.endswith("banned") else AccountRecord.deleted_at
            )
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == target.id)
                .values({column: func.clock_timestamp()})
            )
    assert (
        await claim(SqlChatImageWorkerUnitOfWork(owned.api.sessions))
        == ChatImageProcessingStep.REJECTED
    )
    async with owned.api.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ChatImageAttemptRecord)) == 0
        root = await session.get(ChatImageRecord, image.id)
        assert root is not None
        current = await session.get(ChatImageRevisionRecord, (image.id, root.current_version))
        assert current is not None
        assert current.state == "rejected"
        assert current.failure == (
            "account_unavailable" if reason.startswith("owner") else "contact_unavailable"
        )
